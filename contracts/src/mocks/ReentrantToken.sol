// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MockUCTUSD} from "./MockUCTUSD.sol";

/// @dev Test-only token that calls back into a target when tokens move to
/// `trigger`, to prove the vault cannot be re-entered mid-transfer.
contract ReentrantToken is MockUCTUSD {
    address public target;
    address public trigger;
    bytes public payload;

    function arm(address target_, address trigger_, bytes calldata payload_) external {
        target = target_;
        trigger = trigger_;
        payload = payload_;
    }

    function _update(address from, address to, uint256 value) internal override {
        super._update(from, to, value);
        if (to != address(0) && to == trigger) {
            trigger = address(0); // fire once
            (bool ok, bytes memory ret) = target.call(payload);
            if (!ok) {
                assembly {
                    revert(add(ret, 32), mload(ret))
                }
            }
        }
    }
}
