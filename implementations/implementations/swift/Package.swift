// swift-tools-version: 6.4
import PackageDescription

let package = Package(
    name: "r2t-swift",
    products: [.executable(name: "r2t-swift", targets: ["R2T"])],
    targets: [
        .target(name: "CR2T", cSettings: [
            .unsafeFlags(["-I/usr/include/libmongoc-1.0", "-I/usr/include/libbson-1.0"])
        ], linkerSettings: [
            .linkedLibrary("mongoc-1.0"), .linkedLibrary("bson-1.0"),
            .linkedLibrary("curl"), .linkedLibrary("yaml"), .linkedLibrary("crypto")
        ]),
        .executableTarget(name: "R2T", dependencies: ["CR2T"],
            resources: [.copy("Assets")],
            swiftSettings: [.swiftLanguageMode(.v5)])
    ]
)
