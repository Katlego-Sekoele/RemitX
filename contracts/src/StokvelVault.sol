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

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _exists(bytes32 id) internal view returns (bool) {
        return _stokvels[id].members.length != 0;
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
