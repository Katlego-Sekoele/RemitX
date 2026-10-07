// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title StokvelVault
/// @notice One contract holds every Stokvel, each stored under its own ID.
/// Only opaque IDs and counters live on-chain; names, people and fiat
/// accounts stay in the RemitX database (brief section 7.4).
/// @dev Roles:
///  - DEFAULT_ADMIN_ROLE (Administrator): manages roles; pause/resume (#199).
///  - OPERATOR_ROLE (Treasury Wallet): the only address that creates
///    stokvels, contributes and finalises.
contract StokvelVault is AccessControl, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    uint256 public constant MIN_MEMBERS = 2;
    /// @dev Bounded so loops over members have predictable gas.
    uint256 public constant MAX_MEMBERS = 12;

    struct Stokvel {
        bytes32[] members; // opaque member IDs, in payout order
        uint256 contribution; // fixed amount per member per round
        uint64 startTime; // round 0 opens
        uint64 interval; // time between rounds
        uint8 currentRound; // next round to finalise
        bool closed;
    }

    /// @notice UCTUSD, the token contributions are paid in.
    IERC20 public immutable token;
    /// @notice Where each finalised Pool is sent (see #207).
    address public immutable releaseTarget;

    mapping(bytes32 => Stokvel) internal _stokvels;
    mapping(bytes32 => mapping(bytes32 => bool)) public isMember;
    mapping(bytes32 => mapping(uint8 => mapping(bytes32 => bool))) public paid;
    mapping(bytes32 => mapping(uint8 => uint8)) public paidCount;
    /// @dev Per round, not per stokvel: round N+1 money arrives while round
    /// N's pool is still waiting to be released.
    mapping(bytes32 => mapping(uint8 => uint256)) public roundPool;

    event StokvelCreated(
        bytes32 indexed id,
        bytes32[] members,
        uint256 contribution,
        uint64 startTime,
        uint64 interval
    );
    event StokvelUpdated(
        bytes32 indexed id,
        bytes32[] members,
        uint256 contribution,
        uint64 startTime,
        uint64 interval
    );

    error ZeroAddress();
    error ZeroStokvelId();
    error StokvelExists(bytes32 id);
    error StokvelNotFound(bytes32 id);
    error InvalidMemberCount(uint256 count);
    error ZeroMemberId();
    error DuplicateMember(bytes32 memberId);
    error ZeroContribution();
    error ZeroInterval();
    error StartTimeInPast(uint64 startTime);
    error CycleStarted(bytes32 id);
    error CycleNotStarted(bytes32 id);
    error StokvelIsClosed(bytes32 id);
    error NotMember(bytes32 id, bytes32 memberId);
    error AlreadyPaid(bytes32 id, uint8 round, bytes32 memberId);
    error WrongAmount(uint256 expected, uint256 actual);
    error RoundNotOpen(uint8 round, uint8 openRound);
    error RoundOutOfRange(uint8 round);

    event ContributionMade(
        bytes32 indexed id,
        uint8 indexed round,
        bytes32 indexed memberId,
        uint256 amount
    );
    event RoundFinalised(
        bytes32 indexed id,
        uint8 indexed round,
        bytes32 recipientId,
        uint256 pool
    );
    event StokvelClosed(bytes32 indexed id);

    constructor(
        address admin,
        address operator,
        IERC20 token_,
        address releaseTarget_
    ) {
        if (
            admin == address(0) ||
            operator == address(0) ||
            address(token_) == address(0) ||
            releaseTarget_ == address(0)
        ) revert ZeroAddress();

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, operator);
        token = token_;
        releaseTarget = releaseTarget_;
    }

    // ---------------------------------------------------------------------
    // Operator actions
    // ---------------------------------------------------------------------

    /// @notice Register a new stokvel. Settings can still change until
    /// `startTime`, after which they are fixed for the cycle.
    /// @param id Stokvel ID, e.g. keccak256("stokvel-42").
    /// @param members Opaque member IDs in payout order. Derive each one
    /// off-chain as HMAC(serverSecret, stokvelId || userId), never as a
    /// plain hash of a name, email or sequential ID. A plain hash can be
    /// reversed by guessing inputs, and reusing one ID across stokvels links
    /// a person's groups. Everything here is public and permanent: the
    /// emitted member list stays in the logs even after `updateStokvel`.
    function createStokvel(
        bytes32 id,
        bytes32[] calldata members,
        uint256 contribution,
        uint64 startTime,
        uint64 interval
    ) external onlyRole(OPERATOR_ROLE) {
        if (id == bytes32(0)) revert ZeroStokvelId();
        if (_exists(id)) revert StokvelExists(id);

        _setTerms(id, members, contribution, startTime, interval);

        emit StokvelCreated(id, members, contribution, startTime, interval);
    }

    /// @notice Replace a stokvel's terms before its cycle starts.
    /// @dev Reverts once `block.timestamp >= startTime`: members agreed to
    /// specific terms, and changing them mid-cycle would break that.
    function updateStokvel(
        bytes32 id,
        bytes32[] calldata members,
        uint256 contribution,
        uint64 startTime,
        uint64 interval
    ) external onlyRole(OPERATOR_ROLE) {
        Stokvel storage s = _stokvels[id];
        if (!_exists(id)) revert StokvelNotFound(id);
        if (block.timestamp >= s.startTime) revert CycleStarted(id);

        bytes32[] storage old = s.members;
        for (uint256 i = 0; i < old.length; i++) {
            isMember[id][old[i]] = false;
        }
        delete s.members;

        _setTerms(id, members, contribution, startTime, interval);

        emit StokvelUpdated(id, members, contribution, startTime, interval);
    }

    /// @notice Record one Member's Contribution to a round, pulling the
    /// tokens from the Treasury Wallet. Finalises any round that is ready.
    /// @dev Trust assumption: members hold no keys (brief section 7), so the
    /// contract cannot know who really paid. It trusts the operator to name
    /// the right `memberId`; the backend ledger is the evidence for that.
    ///
    /// Rounds fill in order: round N+1 accepts contributions only once round
    /// N is full. Round N finalises when round N+1 is also full, or at once
    /// if N is the last round. Deadlines are informational, so a late
    /// contribution is still accepted.
    /// @param amount Must equal the stokvel's contribution. Passed explicitly
    /// so a backend amount bug (e.g. wrong decimals) reverts here.
    function contribute(
        bytes32 id,
        uint8 round,
        bytes32 memberId,
        uint256 amount
    ) external onlyRole(OPERATOR_ROLE) whenNotPaused nonReentrant {
        Stokvel storage s = _stokvels[id];
        if (!_exists(id)) revert StokvelNotFound(id);
        if (s.closed) revert StokvelIsClosed(id);
        // Terms can change until the start, so no money may arrive before it.
        if (block.timestamp < s.startTime) revert CycleNotStarted(id);
        uint8 open = _openRound(id, s);
        if (round != open) revert RoundNotOpen(round, open);
        if (!isMember[id][memberId]) revert NotMember(id, memberId);
        if (paid[id][round][memberId]) {
            revert AlreadyPaid(id, round, memberId);
        }
        if (amount != s.contribution) revert WrongAmount(s.contribution, amount);

        paid[id][round][memberId] = true; // mark this member as having paid
        paidCount[id][round] += 1; //increment count of paid members
        roundPool[id][round] += amount; // add to the round's pool
        emit ContributionMade(id, round, memberId, amount); // log the contribution

        token.safeTransferFrom(msg.sender, address(this), amount); // pull the tokens from the Treasury Wallet

        _finaliseReady(id, s); // finalise any rounds that are now ready to be closed
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function getStokvel(
        bytes32 id
    )
        external
        view
        returns (
            bytes32[] memory members,
            uint256 contribution,
            uint64 startTime,
            uint64 interval,
            uint8 currentRound,
            bool closed
        )
    {
        Stokvel storage s = _stokvels[id];
        if (!_exists(id)) revert StokvelNotFound(id);
        return (
            s.members,
            s.contribution,
            s.startTime,
            s.interval,
            s.currentRound,
            s.closed
        );
    }

    function exists(bytes32 id) external view returns (bool) {
        return _exists(id);
    }

    /// @notice Whether the cycle has started, i.e. the terms are fixed.
    function hasStarted(bytes32 id) external view returns (bool) {
        if (!_exists(id)) revert StokvelNotFound(id);
        return block.timestamp >= _stokvels[id].startTime;
    }

    /// @notice The only round that currently accepts contributions.
    function openRound(bytes32 id) external view returns (uint8) {
        Stokvel storage s = _stokvels[id];
        if (!_exists(id)) revert StokvelNotFound(id);
        if (s.closed) revert StokvelIsClosed(id);
        return _openRound(id, s);
    }

    /// @notice Scheduled payout time (the round's Deadline). Informational:
    /// a round actually finalises when the next round fills, not on a timer.
    function payoutTime(bytes32 id, uint8 round) external view returns (uint256) {
        Stokvel storage s = _stokvels[id];
        if (!_exists(id)) revert StokvelNotFound(id);
        if (round >= s.members.length) revert RoundOutOfRange(round);
        // uint256 maths so extreme start/interval values cannot overflow.
        return uint256(s.startTime) + (uint256(round) + 1) * s.interval;
    }

    /// @notice The member entitled to the next round to finalise.
    function nextRecipient(bytes32 id) external view returns (bytes32) {
        Stokvel storage s = _stokvels[id];
        if (!_exists(id)) revert StokvelNotFound(id);
        if (s.closed) revert StokvelIsClosed(id);
        return s.members[s.currentRound];
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _exists(bytes32 id) internal view returns (bool) {
        return _stokvels[id].members.length != 0;
    }

    /// @dev The round after the last one to finalise, once that one is full.
    function _openRound(
        bytes32 id,
        Stokvel storage s
    ) internal view returns (uint8) {
        uint8 r = s.currentRound;
        return paidCount[id][r] == s.members.length ? r + 1 : r;
    }

    /// @dev Finalises every round that is ready: at most two per call (the
    /// second-last and last rounds finalise together). State is zeroed and
    /// advanced before each transfer, so a reentrant call finds nothing left
    /// to release (and `nonReentrant` blocks it anyway).
    function _finaliseReady(bytes32 id, Stokvel storage s) internal {
        uint256 n = s.members.length; // members = number of rounds in cycle, one per member
        while (!s.closed) { // stop once the last round finalises and closes the cycle
            uint8 r = s.currentRound; // the round to finalise, if full
            if (paidCount[id][r] != n) return; // if not full yet do nothing
            bool last = r + 1 == n; // the last round finalises immediately, no next round to wait for
            if (!last && paidCount[id][r + 1] != n) return; // if not last, wait for the next round to fill before finalising

            uint256 pool = roundPool[id][r];
            roundPool[id][r] = 0; //empty the pool before transferring, so a reentrant call finds nothing to release
            s.currentRound = r + 1; //move to the next round before transferring, so a reentrant call finds nothing to release
            if (last) s.closed = true; //close after final round

            emit RoundFinalised(id, r, s.members[r], pool); //who recieives it and how much
            if (last) emit StokvelClosed(id);

            token.safeTransfer(releaseTarget, pool); //move te tokens
        }
    }

    /// @dev Validates and writes terms. Expects `members` to be empty.
    function _setTerms(
        bytes32 id,
        bytes32[] calldata members,
        uint256 contribution,
        uint64 startTime,
        uint64 interval
    ) internal {
        uint256 count = members.length;
        if (count < MIN_MEMBERS || count > MAX_MEMBERS) {
            revert InvalidMemberCount(count);
        }
        if (contribution == 0) revert ZeroContribution();
        if (interval == 0) revert ZeroInterval();
        if (startTime < block.timestamp) revert StartTimeInPast(startTime);

        Stokvel storage s = _stokvels[id];
        for (uint256 i = 0; i < count; i++) {
            bytes32 m = members[i];
            if (m == bytes32(0)) revert ZeroMemberId();
            if (isMember[id][m]) revert DuplicateMember(m);
            isMember[id][m] = true;
            s.members.push(m);
        }
        s.contribution = contribution;
        s.startTime = startTime;
        s.interval = interval;
    }
}
