// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MockUCTUSD} from "./MockUCTUSD.sol";

/// @dev Test-only token that burns 1% of every transfer, so the receiver
/// gets less than was sent. Proves the vault rejects a short contribution.
contract FeeOnTransferToken is MockUCTUSD {
    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            uint256 fee = value / 100;
            super._update(from, address(0), fee);
            super._update(from, to, value - fee);
        } else {
            super._update(from, to, value);
        }
    }
}
