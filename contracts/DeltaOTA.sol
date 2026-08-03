// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract DeltaOTA {
    // Struct tailored for Phase 3 Edge Gateway polling and gas efficiency
    struct FirmwareRelease {
        bytes32 version; // e.g., "v1.1" stored as bytes32 for fixed storage slot allocation
        bytes32 goldenHash; // SHA-256 hash of the delta patch generated from the Developer Console
        string ipfsUrl; // Payload hosting URL for Edge Gateway retrieval
        uint8 approvalCount; // Counter for authorized developer signatures
        bool isLive; // State flag indicating M-of-N threshold (2 signatures) has been reached
        bool isRevoked; // Emergency Kill Switch flag
    }

    // State storage mappings
    mapping(bytes32 => FirmwareRelease) public releases; // Maps version -> FirmwareRelease struct
    mapping(bytes32 => mapping(address => bool)) public hasSigned; // Maps version -> dev address -> signature status
    mapping(address => bool) public authorizedDevelopers; // Whitelist mapping for active developers

    // Administrative and Multi-signature variables (Fixed at 3 Devs, 2 Threshold)
    uint8 public constant thresholdM = 2; // Minimum signatures required for Live status
    uint8 public constant totalDevelopersN = 3; // Total registered developers

    // Events for Phase 3 Edge Gateway telemetry
    event DeveloperStatusUpdated(address indexed developer, bool status);
    event ReleaseProposed(
        bytes32 version,
        bytes32 goldenHash,
        string ipfsUrl,
        address indexed proposer
    );
    event ReleaseApproved(
        bytes32 version,
        address indexed approver,
        uint8 currentApprovals
    );
    
    // Optimized event: Broadcasts all metadata so the Gateway does not need a secondary getter call
    event ReleasePromotedToLive(
        bytes32 version, 
        bytes32 goldenHash, 
        string ipfsUrl
    );
    
    event ReleaseRevoked(bytes32 version, address indexed revoker);

    // Modifier to enforce Zero Trust access control based on the developer whitelist
    modifier onlyAuthorized() {
        require(
            authorizedDevelopers[msg.sender],
            "Unauthorized: Caller is not a registered developer"
        );
        _;
    }

    // Modifier to verify the proposal exists in the registry prior to state transitions
    modifier releaseExists(bytes32 version) {
        require(
            releases[version].version != bytes32(0),
            "Registry Error: Firmware version does not exist"
        );
        _;
    }

    // Constructor initializes the registry with a fixed array of authorized developers
    constructor(address[] memory initialDevelopers) {
        require(
            initialDevelopers.length == 3,
            "Initialization Error: Exactly 3 initial developers required"
        );

        // Populate the blockchain storage with the developer addresses
        for (uint256 i = 0; i < initialDevelopers.length; i++) {
            address dev = initialDevelopers[i];
            require(dev != address(0), "Initialization Error: Invalid zero address");
            require(!authorizedDevelopers[dev], "Initialization Error: Duplicate developer address");

            authorizedDevelopers[dev] = true;

            emit DeveloperStatusUpdated(dev, true);
        }
    }

    // Step 1: Submission of a new firmware release proposal from the Developer Console
    function proposeRelease(
        bytes32 version,
        bytes32 goldenHash,
        string calldata ipfsUrl
    ) external onlyAuthorized {
        // Prevent duplicate version entries to maintain ledger integrity
        require(
            releases[version].version == bytes32(0),
            "Registry Error: Release version already exists"
        );
        require(goldenHash != bytes32(0), "Validation Error: Golden Hash cannot be empty");

        releases[version] = FirmwareRelease({
            version: version,
            goldenHash: goldenHash,
            ipfsUrl: ipfsUrl,
            approvalCount: 1,
            isLive: (1 >= thresholdM),
            isRevoked: false
        });

        // Record the proposer's signature to prevent double-voting in approveRelease()
        hasSigned[version][msg.sender] = true;

        emit ReleaseProposed(version, goldenHash, ipfsUrl, msg.sender);
        emit ReleaseApproved(version, msg.sender, 1);
    }

    // Step 2: Multi-signature approval to reach the required M-of-N threshold
    function approveRelease(
        bytes32 version
    ) external onlyAuthorized releaseExists(version) {
        FirmwareRelease storage release = releases[version];

        // Cryptographic and state validation checks prior to counting the signature
        require(!release.isRevoked, "Governance Error: Cannot approve a revoked release");
        require(!release.isLive, "Governance Error: Release is already Live");
        require(
            !hasSigned[version][msg.sender],
            "Governance Error: Developer has already signed this release"
        );

        // Record the cryptographic signature
        hasSigned[version][msg.sender] = true;
        release.approvalCount++;

        emit ReleaseApproved(version, msg.sender, release.approvalCount);

        // State Transition: Promote to Live if the threshold is met
        if (release.approvalCount >= thresholdM) {
            release.isLive = true;
            emit ReleasePromotedToLive(version, release.goldenHash, release.ipfsUrl);
        }
    }

    // Unilateral Kill Switch: Triggered upon detection of an exploit to revoke distribution
    function revokeRelease(
        bytes32 version
    ) external onlyAuthorized releaseExists(version) {
        FirmwareRelease storage release = releases[version];
        require(!release.isRevoked, "Governance Error: Release is already revoked");

        release.isRevoked = true;
        
        // Immediately strip Live status to halt Gateway distribution
        release.isLive = false; 

        emit ReleaseRevoked(version, msg.sender);
    }

    // Helper function for the Python Edge Gateway to poll ledger state
    function getRelease(
        bytes32 version
    ) external view returns (FirmwareRelease memory) {
        return releases[version];
    }
}
