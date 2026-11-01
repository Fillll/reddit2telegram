import Foundation
import CR2T

// Never start a partial port against the production queue. Source coverage and
// successful compilation must be reviewed before this is enabled.
let fullPortComplete = true
let args = Array(CommandLine.arguments.dropFirst())
do {
    if args.contains("--describe") {
        r2t_init()
        var assets: [String: String] = [:]
        for name in ["local_channels", "weighted_channel", "milestones"] {
            guard let path = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Assets") else { throw R2TError.config }
            assets[name] = try digest(String(contentsOf: path, encoding: .utf8))
        }
        print(try json(["language": "swift", "compiler": BuildInfo.compiler,
            "source_commit": BuildInfo.commit, "version": BuildInfo.version,
            "full_port_complete": fullPortComplete, "profile": "release -O",
            "language_mode": "Swift 5 mode; Swift 6.4.2 compiler", "configuration_sha256": assets,
            "mongodb_client": String(cString: r2t_mongoc_version()),
            "http_client": String(cString: r2t_curl_version())]))
    } else if args.contains("--version") {
        print("r2t-swift " + BuildInfo.version)
    } else {
        guard fullPortComplete else { throw R2TError.incompletePort }
        let filename: String
        if let index = args.firstIndex(of: "--config"), index + 1 < args.count { filename = args[index + 1] }
        else { filename = "configs/prod.yml" }
        let config = try Config(path: filename)
        let arenas = Int(number(object(config.values["pool"])["malloc_arenas"], 4))
        guard arenas > 0 && arenas <= Int(Int32.max) else { throw R2TError.config }
        r2t_allocator(Int32(arenas), 0)
        log("Limited native allocator to \(arenas) arenas")
        let reporter = try Reporter(config: config); defer { reporter.close() }
        let role = args.first ?? "consumer"
        do {
            let app = try App(config: config, reporter: reporter)
            switch role {
            case "consumer": try consumer(app)
            case "scheduler": try scheduler(app)
            default: throw R2TError.config
            }
        } catch { reporter.capture(error, module: role); throw error }
    }
} catch {
    log("r2t-swift: \(safeError(error))", warning: true)
    exit(1)
}
