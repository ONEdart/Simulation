pragma solidity ^0.8.0;

contract Storage {
    uint256 private data = 846;
    function set(uint256 x) public { data = x; }
    function get() public view returns (uint256) { return data; }
}
