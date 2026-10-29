// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title StokvelVault
/// @notice One contract holds every Stokvel (doc D4). A stokvel is
/// registered once with its contribution, then runs one cycle at a time;
/// each cycle fixes its members (payout order) and its round schedule.
/// Only opaque IDs, amounts and times live on-chain; names, people and fiat
/// accounts stay in the RemitX database.
/// @dev Interface: docs/stokvel_integration.md section 1.
///
/// Roles:
///  - DEFAULT_ADMIN_ROLE (Administrator): manages roles; pause and resume.
///    Must not be the operator, so the key that moves tokens cannot also
///    control the emergency stop.
///  - OPERATOR_ROLE (Treasury Wallet, used by the backend): creates
///    stokvels, starts cycles, contributes and finalises.
///
/// Trust assumption: members hold no keys, so the contract cannot know who
/// really paid. It trusts the operator to name the right member; the
/// backend ledger is the evidence for that.
///
/// Release rule (doc D5, D12): round N releases once every member has paid
/// round N+1 (or N is the last round and is fully paid) AND round N's
/// payout time has passed. The contribution deadline is informational.
contract StokvelVault is AccessControl, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    uint8 public constant MIN_MEMBERS = 2;

    struct Stokvel {
        uint256 contribution; // fixed UCTUSD amount per member per round
        uint32 currentCycle; // 0 until the first cycle starts
        bool exists;
    }

    struct Cycle {
        bytes32[] members; // payout order: round i pays members[i]
        uint64[] roundStartTimes; // informational
        uint64[] roundDeadlines; // informational (doc D7)
        uint64[] payoutTimes; // hard gate for release (doc D12)
        uint8 nextToFinalise; // rounds below this are finalised
        bool closed;
    }

    /// @notice UCTUSD, the token contributions are paid in.
    IERC20 public immutable token;
    /// @notice Where each released Pool is sent (the Treasury Wallet, D2).
    address public immutable releaseTarget;
    /// @notice Member cap, set at deployment (3 for the prototype, P3).
    uint8 public immutable maxMembers;

    mapping(bytes32 => Stokvel) internal _stokvels;
    mapping(bytes32 => mapping(uint32 => Cycle)) internal _cycles;
    mapping(bytes32 => mapping(uint32 => mapping(bytes32 => bool)))
        internal _isMember;
    mapping(bytes32 => mapping(uint32 => mapping(uint8 => mapping(bytes32 => bool))))
        internal _paid;
    mapping(bytes32 => mapping(uint32 => mapping(uint8 => uint8)))
        internal _paidCount;
    /// @dev Per round, not per stokvel: later rounds' money arrives while an
    /// earlier round's pool is still waiting to be released.
    mapping(bytes32 => mapping(uint32 => mapping(uint8 => uint256)))
        internal _roundPool;

    event StokvelCreated(bytes32 indexed id, uint256 contribution);
    event CycleStarted(bytes32 indexed id, uint32 cycle);
    event ContributionMade(
        bytes32 indexed id,
        uint32 cycle,
        uint8 round,
        bytes32 indexed memberId,
        uint256 amount
    );
    event RoundFinalised(
        bytes32 indexed id,
        uint32 cycle,
        uint8 round,
        bytes32 indexed memberId,
        uint256 pool
    );
    event CycleClosed(bytes32 indexed id, uint32 cycle);

    // Errors named in doc section 1.
    error NotMember(bytes32 memberId);
    error AlreadyPaid(uint8 round, bytes32 memberId);
    error WrongRound(uint8 round, uint8 openRound);
    error WrongAmount(uint256 expected, uint256 received);
    error NotYetFinalisable(uint8 round);
    error AlreadyFinalised(uint8 round);
    error CycleNotOpen(bytes32 id);
    error UnknownStokvel(bytes32 id);
    error MaxMembersExceeded(uint256 count, uint8 maxMembers);
    // Input validation.
    error ZeroAddress();
    error AdminIsOperator();
    error InvalidMaxMembers(uint8 maxMembers);
    error ZeroId();
    error StokvelExists(bytes32 id);
    error ZeroContribution();
    error CycleInProgress(bytes32 id);
    error TooFewMembers(uint256 count);
    error ZeroMemberId();
    error DuplicateMember(bytes32 memberId);
    error ScheduleLengthMismatch();
    error InvalidSchedule(uint8 round);
    error UnknownCycle(uint32 cycle);

    constructor(
        address admin,
        address operator,
        IERC20 token_,
        address releaseTarget_,
        uint8 maxMembers_
    ) {
        if (
            admin == address(0) ||
            operator == address(0) ||
            address(token_) == address(0) ||
            releaseTarget_ == address(0)
        ) revert ZeroAddress();
        // The key that moves tokens must not also hold the emergency stop.
        if (admin == operator) revert AdminIsOperator();
        if (maxMembers_ < MIN_MEMBERS) revert InvalidMaxMembers(maxMembers_);

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, operator);
        token = token_;
        releaseTarget = releaseTarget_;
        maxMembers = maxMembers_;
    }

    // ---------------------------------------------------------------------
    // Administrator actions
    // ---------------------------------------------------------------------

    /// @notice Emergency stop for every stokvel at once. While paused,
    /// `contribute` and `finalise` revert, so no tokens move. State is
    /// untouched, so resuming restores it exactly.
    /// @dev Creating stokvels and starting cycles stay available: they move
    /// no tokens, and the Administrator has no say over a group's terms.
    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    /// @notice Resume after `pause`. Release conditions are unchanged.
    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    // ---------------------------------------------------------------------
    // Operator actions
    // ---------------------------------------------------------------------

    /// @notice Register a stokvel and its fixed contribution.
    /// @param id Database UUID packed left-aligned into bytes32.
    /// @param contribution UCTUSD smallest units (18 decimals).
    function createStokvel(
        bytes32 id,
        uint256 contribution
    ) external onlyRole(OPERATOR_ROLE) {
        if (id == bytes32(0)) revert ZeroId();
        if (_stokvels[id].exists) revert StokvelExists(id);
        if (contribution == 0) revert ZeroContribution();

        _stokvels[id] = Stokvel({
            contribution: contribution,
            currentCycle: 0,
            exists: true
        });
        emit StokvelCreated(id, contribution);
    }

    /// @notice Start the next cycle: fix its members and its schedule.
    /// Only when no cycle is open (the first, or after the last one closed).
    /// @param memberIds Opaque member IDs in payout order; round i pays
    /// memberIds[i]. Use a per-stokvel ID (e.g. the stokvel_members row
    /// UUID), not the user's ID, so one person's stokvels cannot be linked
    /// on-chain. Everything here is public and permanent.
    /// @param roundStartTimes Informational.
    /// @param roundDeadlines Informational: late contributions are accepted.
    /// @param payoutTimes Enforced: round i cannot release before
    /// payoutTimes[i]. Each round needs start <= deadline <= payout, and
    /// start and payout times may not go backwards from round to round.
    function startCycle(
        bytes32 id,
        bytes32[] calldata memberIds,
        uint64[] calldata roundStartTimes,
        uint64[] calldata roundDeadlines,
        uint64[] calldata payoutTimes
    ) external onlyRole(OPERATOR_ROLE) {
        uint32 cycle = _beginCycle(id, memberIds);
        _validateSchedule(
            memberIds.length,
            roundStartTimes,
            roundDeadlines,
            payoutTimes
        );
        Cycle storage c = _cycles[id][cycle];
        c.roundStartTimes = roundStartTimes;
        c.roundDeadlines = roundDeadlines;
        c.payoutTimes = payoutTimes;

        emit CycleStarted(id, cycle);
    }

    /// @notice Record one Member's Contribution, pulling exactly the
    /// stokvel's contribution from the Treasury Wallet. Releases any round
    /// that has become due.
    /// @dev Rounds fill in order: a round accepts contributions only once
    /// every earlier round is fully paid. Deadlines are informational.
    /// A repeat payment is checked before the round, so it always reports
    /// `AlreadyPaid`, even once that round has filled and the open round
    /// has moved on.
    function contribute(
        bytes32 id,
        uint8 round,
        bytes32 memberId
    ) external onlyRole(OPERATOR_ROLE) whenNotPaused nonReentrant {
        (Stokvel storage s, uint32 cycle, Cycle storage c) = _openCycle(id);
        if (!_isMember[id][cycle][memberId]) revert NotMember(memberId);
        if (_paid[id][cycle][round][memberId]) {
            revert AlreadyPaid(round, memberId);
        }
        uint8 open = _openRound(id, cycle, c);
        // `open` equals the member count once every round is paid; no round
        // that high exists, so nothing may be paid into it.
        if (round != open || open >= c.members.length) {
            revert WrongRound(round, open);
        }

        uint256 amount = s.contribution;
        _paid[id][cycle][round][memberId] = true;
        _paidCount[id][cycle][round] += 1;
        _roundPool[id][cycle][round] += amount;

        // Measure what arrived, so a token that takes a fee or misreports
        // a transfer cannot leave the pool short.
        uint256 before = token.balanceOf(address(this));
        token.safeTransferFrom(msg.sender, address(this), amount);
        uint256 received = token.balanceOf(address(this)) - before;
        if (received != amount) revert WrongAmount(amount, received);

        emit ContributionMade(id, cycle, round, memberId, amount);

        _releaseDue(id, cycle, c);
    }

    /// @notice Release one round's pool once its conditions hold. Called by
    /// the backend's scheduled task for rounds that become due with time
    /// rather than with a contribution, and by the Administrator fallback.
    /// @dev Reverts `NotYetFinalisable` if the round is not the next to
    /// release, is not fully paid, the next round is not fully paid, or the
    /// payout time has not passed.
    function finalise(
        bytes32 id,
        uint8 round
    ) external onlyRole(OPERATOR_ROLE) whenNotPaused nonReentrant {
        Stokvel storage s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        uint32 cycle = s.currentCycle;
        if (cycle == 0) revert CycleNotOpen(id);
        Cycle storage c = _cycles[id][cycle];
        if (round < c.nextToFinalise) revert AlreadyFinalised(round);
        if (c.closed) revert CycleNotOpen(id);
        if (!_isFinalisable(id, cycle, c, round)) {
            revert NotYetFinalisable(round);
        }
        _release(id, cycle, c, round);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    /// @return contribution Fixed UCTUSD amount per member per round.
    /// @return currentCycle The latest cycle (0 if none started yet).
    /// @return cycleOpen Whether that cycle is running.
    function getStokvel(
        bytes32 id
    )
        external
        view
        returns (uint256 contribution, uint32 currentCycle, bool cycleOpen)
    {
        Stokvel storage s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        uint32 cycle = s.currentCycle;
        return (s.contribution, cycle, cycle != 0 && !_cycles[id][cycle].closed);
    }

    /// @notice A cycle's members, schedule and progress.
    /// @dev `nextToFinalise`: rounds below it have been released.
    function getCycle(
        bytes32 id,
        uint32 cycle
    )
        external
        view
        returns (
            bytes32[] memory members,
            uint64[] memory roundStartTimes,
            uint64[] memory roundDeadlines,
            uint64[] memory payoutTimes,
            uint8 nextToFinalise,
            bool closed
        )
    {
        Stokvel storage s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        if (cycle == 0 || cycle > s.currentCycle) revert UnknownCycle(cycle);
        Cycle storage c = _cycles[id][cycle];
        return (
            c.members,
            c.roundStartTimes,
            c.roundDeadlines,
            c.payoutTimes,
            c.nextToFinalise,
            c.closed
        );
    }

    /// @notice Whether a member has paid a round of the current cycle.
    function hasPaid(
        bytes32 id,
        uint8 round,
        bytes32 memberId
    ) external view returns (bool) {
        return _paid[id][_latestCycle(id)][round][memberId];
    }

    /// @notice Whether an ID is a member of the current cycle.
    function isMember(
        bytes32 id,
        bytes32 memberId
    ) external view returns (bool) {
        return _isMember[id][_latestCycle(id)][memberId];
    }

    /// @notice Tokens held for a round of the current cycle (0 once
    /// released).
    function roundPool(bytes32 id, uint8 round) external view returns (uint256) {
        return _roundPool[id][_latestCycle(id)][round];
    }

    /// @notice How many members have paid a round of the current cycle.
    function paidCount(bytes32 id, uint8 round) external view returns (uint8) {
        return _paidCount[id][_latestCycle(id)][round];
    }

    /// @notice Whether `finalise(id, round)` would succeed now (ignoring
    /// pause). The backend's scheduled task polls this.
    function isFinalisable(
        bytes32 id,
        uint8 round
    ) external view returns (bool) {
        Stokvel storage s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        uint32 cycle = s.currentCycle;
        if (cycle == 0) return false;
        Cycle storage c = _cycles[id][cycle];
        return !c.closed && _isFinalisable(id, cycle, c, round);
    }

    /// @notice The only round that currently accepts contributions. Equals
    /// the member count once every round is paid (none left to pay).
    function openRound(bytes32 id) external view returns (uint8) {
        (, uint32 cycle, Cycle storage c) = _openCycle(id);
        return _openRound(id, cycle, c);
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _validateSchedule(
        uint256 n,
        uint64[] calldata starts,
        uint64[] calldata deadlines,
        uint64[] calldata payouts
    ) internal pure {
        if (starts.length != n || deadlines.length != n || payouts.length != n) {
            revert ScheduleLengthMismatch();
        }
        for (uint256 i = 0; i < n; i++) {
            if (
                starts[i] > deadlines[i] ||
                deadlines[i] > payouts[i] ||
                (i > 0 &&
                    (starts[i] < starts[i - 1] || payouts[i] < payouts[i - 1]))
            ) revert InvalidSchedule(uint8(i));
        }
    }

    /// @dev Checks the stokvel can start a cycle, opens the next cycle and
    /// fixes its members. Returns the new cycle number.
    function _beginCycle(
        bytes32 id,
        bytes32[] calldata memberIds
    ) internal returns (uint32 cycle) {
        Stokvel storage s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        if (s.currentCycle != 0 && !_cycles[id][s.currentCycle].closed) {
            revert CycleInProgress(id);
        }
        uint256 n = memberIds.length;
        if (n < MIN_MEMBERS) revert TooFewMembers(n);
        if (n > maxMembers) revert MaxMembersExceeded(n, maxMembers);

        cycle = s.currentCycle + 1;
        s.currentCycle = cycle;
        Cycle storage c = _cycles[id][cycle];
        for (uint256 i = 0; i < n; i++) {
            bytes32 m = memberIds[i];
            if (m == bytes32(0)) revert ZeroMemberId();
            if (_isMember[id][cycle][m]) revert DuplicateMember(m);
            _isMember[id][cycle][m] = true;
            c.members.push(m);
        }
    }

    function _openCycle(
        bytes32 id
    ) internal view returns (Stokvel storage s, uint32 cycle, Cycle storage c) {
        s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        cycle = s.currentCycle;
        c = _cycles[id][cycle];
        if (cycle == 0 || c.closed) revert CycleNotOpen(id);
    }

    function _latestCycle(bytes32 id) internal view returns (uint32) {
        Stokvel storage s = _stokvels[id];
        if (!s.exists) revert UnknownStokvel(id);
        return s.currentCycle;
    }

    /// @dev First round, from the next to release, that is not fully paid.
    function _openRound(
        bytes32 id,
        uint32 cycle,
        Cycle storage c
    ) internal view returns (uint8) {
        uint256 n = c.members.length;
        uint8 r = c.nextToFinalise;
        while (r < n && _paidCount[id][cycle][r] == n) r++;
        return r;
    }

    function _isFinalisable(
        bytes32 id,
        uint32 cycle,
        Cycle storage c,
        uint8 round
    ) internal view returns (bool) {
        uint256 n = c.members.length;
        if (round != c.nextToFinalise || round >= n) return false;
        if (_paidCount[id][cycle][round] != n) return false;
        if (round + 1 < n && _paidCount[id][cycle][round + 1] != n) {
            return false;
        }
        return block.timestamp >= c.payoutTimes[round];
    }

    /// @dev Releases every round that is due, in order. Rounds wait only on
    /// payment or on time, so this releases at most the rounds whose
    /// payout times have already passed.
    function _releaseDue(bytes32 id, uint32 cycle, Cycle storage c) internal {
        while (!c.closed && _isFinalisable(id, cycle, c, c.nextToFinalise)) {
            _release(id, cycle, c, c.nextToFinalise);
        }
    }

    /// @dev State is zeroed and advanced before the transfer, so a
    /// reentrant call finds nothing left to release (and `nonReentrant`
    /// blocks it anyway).
    function _release(
        bytes32 id,
        uint32 cycle,
        Cycle storage c,
        uint8 round
    ) internal {
        uint256 pool = _roundPool[id][cycle][round];
        _roundPool[id][cycle][round] = 0;
        c.nextToFinalise = round + 1;
        bool last = round + 1 == c.members.length;
        if (last) c.closed = true;

        emit RoundFinalised(id, cycle, round, c.members[round], pool);
        if (last) emit CycleClosed(id, cycle);

        token.safeTransfer(releaseTarget, pool);
    }
}
