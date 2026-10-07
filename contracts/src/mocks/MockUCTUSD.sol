// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Test-only stand-in for UCTUSD. Never deployed.
contract MockUCTUSD is ERC20 {
    constructor() ERC20("Mock UCTUSD", "UCTUSD") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
