import Foundation
import CR2T

// Never start a partial port against the production queue. Source coverage and
// successful compilation must be reviewed before this is enabled.
let fullPortComplete = false
let args = Array(CommandLine.arguments.dropFirst())
do {
    if args.contains("--describe") {
        r2t_init()
        print(try json(["language": "swift", "compiler": BuildInfo.compiler,
            "source_commit": BuildInfo.commit, "version": BuildInfo.version,
            "full_port_complete": fullPortComplete, "profile": "release -O",
            "mongodb_client": String(cString: r2t_mongoc_version()),
            "http_client": String(cString: r2t_curl_version())]))
    } else if args.contains("--version") {
        print("r2t-swift " + BuildInfo.version)
    } else {
        guard fullPortComplete else { throw R2TError.incompletePort }
        throw R2TError.unknownTask
    }
} catch {
    log("r2t-swift: \(safeError(error))", warning: true)
    exit(1)
}
