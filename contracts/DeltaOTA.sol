// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract DeltaOTA {
    // Struct para uniform sa Phase 3 Edge Gateway polling
    struct FirmwareRelease {
        string version; // e.g. "v1.1"
        bytes32 goldenHash; // SHA-256 hash ng delta patch galing sa Phase 1 GUI
        string ipfsUrl; // URL kung saan idi-download ng Edge Gateway yung patch
        uint8 approvalCount; // Counter ng nag-approve na authorized developers
        bool isLive; // Mag-m-true lang 'to 'pag naabot na yung M-of-N threshold (2 signatures)
        bool isRevoked; // Emergency Kill-Switch flag
    }

    // State storage mappings
    mapping(string version=> FirmwareRelease) public releases; // Maps version string -> FirmwareRelease struct
    mapping(string version => mapping(address developerAddress=> bool)) public hasSigned; // Maps version string -> dev address -> has standard approval status
    mapping(address developerAddress => bool) public authorizedDevelopers; // Whitelist mapping para sa active developers

    // Administrative at Multi-sig variables (Fixed at 3 Devs, 2 Threshold)
    uint8 public constant thresholdM = 2; // Minimum 2 signatures na kailangan para maging Live
    uint8 public constant totalDevelopersN = 3; // Total 3 registered developers

    // Events para sa polling ng Phase 3 Edge Gateway
    event DeveloperStatusUpdated(address indexed developer, bool status);
    event ReleaseProposed(
        string version,
        bytes32 goldenHash,
        string ipfsUrl,
        address indexed proposer
    );
    event ReleaseApproved(
        string version,
        address indexed approver,
        uint8 currentApprovals
    );
    event ReleasePromotedToLive(string version);
    event ReleaseRevoked(string version, address indexed revoker);

    // Modifier para macheck kung nasa authorizedDevelopers mapping ang wallet address from Phase 1
    modifier onlyAuthorized() {
        require(
            authorizedDevelopers[msg.sender],
            "This is not an authorized developer"
        );
        _;
    }

    // Check muna kung na-propose na talaga yung version sa registry bago i-process
    modifier releaseExists(string memory version) {
        require(
            bytes(releases[version].version).length > 0,
            "Version does not exist"
        );
        _;
    }

    // Constructor: the concept is i-initialize ang admin at ililist kagad yung 3 authorized developers
    // idedeclare na kaagad na 3 devs ang papasok sa system, tama ba?
    constructor(address[] memory initialDevelopers) {
        require(
            initialDevelopers.length == 3,
            "Exactly 3 initial developers required"
        );

        // Loop para ma-populate sa blockchain storage yung 3 developer addresses
        for (uint256 i = 0; i < initialDevelopers.length; i++) {
            address dev = initialDevelopers[i];
            require(dev != address(0), "Invalid address");
            require(!authorizedDevelopers[dev], "Duplicate developer address");

            authorizedDevelopers[dev] = true;

            emit DeveloperStatusUpdated(dev, true);
        }
    }

    // Step 1: submission ng bagong firmware release proposal galing sa Phase 1 GUI
    function proposeRelease(
        string calldata version,
        bytes32 goldenHash,
        string calldata ipfsUrl
    ) external onlyAuthorized {
        // Iwas duplicate version entries
        require(
            bytes(releases[version].version).length == 0,
            "Release version already exists"
        );
        require(goldenHash != bytes32(0), "Golden Hash cannot be empty");

        releases[version] = FirmwareRelease({
            version: version,
            goldenHash: goldenHash,
            ipfsUrl: ipfsUrl,
            approvalCount: 1,
            isLive: (1 >= thresholdM),
            isRevoked: false
        });

        // I-mark na nag-sign na si proposer para 'di na siya maka-double vote sa approveRelease()
        hasSigned[version][msg.sender] = true;

        emit ReleaseProposed(version, goldenHash, ipfsUrl, msg.sender);
        emit ReleaseApproved(version, msg.sender, 1);
    }

    // Step 2: Pag-sign/approve ng pangalawang authorized developer para maabot ang 2/3 threshold
    function approveRelease(
        string calldata version
    ) external onlyAuthorized releaseExists(version) {
        FirmwareRelease storage release = releases[version];

        // Safety checks bago i-count ang vote
        require(!release.isRevoked, "Cannot approve a revoked release");
        require(!release.isLive, "Release is already Live");
        require(
            !hasSigned[version][msg.sender],
            "Developer has already signed this release"
        );

        // Record na nag-sign na 'tong dev wallet
        hasSigned[version][msg.sender] = true;
        release.approvalCount++;

        emit ReleaseApproved(version, msg.sender, release.approvalCount);

        // State Transition: Kapag naabot na ang 2/3 signatures (approvalCount >= 2), magfi-flip na to Live
        if (release.approvalCount >= thresholdM) {
            release.isLive = true;
            emit ReleasePromotedToLive(version);
        }
    }

    // Kill-Switch: Pwedeng i-trigger ng authorized dev kapag may na-detect na exploit sa patch
    function revokeRelease(
        string calldata version
    ) external onlyAuthorized releaseExists(version) {
        FirmwareRelease storage release = releases[version];
        require(!release.isRevoked, "Release is already revoked");

        release.isRevoked = true;
        release.isLive = false; // Bawiin agad yung Live status para 'di na i-serve ng Gateway

        emit ReleaseRevoked(version, msg.sender);
    }

    // Helper getter function para sa Python Web3.py polling ng Phase 3 Edge Gateway
    function getRelease(
        string calldata version
    ) external view returns (FirmwareRelease memory) {
        return releases[version];
    }
}
