import Foundation
import CR2T

struct ErrorContext { var channel: String?; var link: String? }
final class App {
    let config: Config
    let db: Database
    let videos: DispatchSemaphore
    let reporter: Reporter
    init(config: Config, db: Database? = nil, videos: DispatchSemaphore = DispatchSemaphore(value: 2), reporter: Reporter) throws {
        self.config = config; self.db = try db ?? config.database(); self.videos = videos; self.reporter = reporter
    }
    func sender(_ destination: Any, metrics: Metrics) throws -> Sender {
        try Sender(config: config, db: db, destination: destination, metrics: metrics, videos: videos)
    }
    func runJob(_ task: Doc) {
        let args = object(task["args"]); let module = text(args["submodule_name"])
        let metrics = Metrics(root: config.root, taskID: idString(task["_id"]), module: module,
            created: (task["created_at"] as? NSNumber)?.doubleValue)
        let filter: Doc = ["_id": task["_id"] ?? null]
        var outcome: Error?
        do {
            log("Modified \(try db.update("tasks", filter, ["$set": ["status": 2, "updated_at": now()]])) docs")
            guard text(task["name"]) == "supply" else { throw R2TError.unknownTask }
            var next = config
            if let values = args["config"] as? Doc { next.values = values }
            else if let filename = args["config_filename"] as? String { next = try Config(path: filename) }
            let sameDatabase = try json(next.values["db"] ?? null) == json(config.values["db"] ?? null)
            let job = try App(config: next, db: sameDatabase ? db : nil, videos: videos, reporter: reporter)
            var context = ErrorContext()
            do { try job.supply(module, metrics: metrics, context: &context) }
            catch {
                reporter.capture(error, module: module)
                do { try reportDeveloper(job, module: module, context: context, error: error, metrics: metrics) }
                catch { log("developer reporting failed for \(module)", warning: true) }
                throw error
            }
            log("Modified \(try db.update("tasks", filter, ["$set": ["status": 3, "updated_at": now()]])) docs")
            log("Task supply successfully executed.")
        } catch {
            outcome = error
            log("Task supply failed: \(safeError(error))", warning: true)
            do { log("Modified \(try db.update("tasks", filter, ["$set": ["status": 4, "updated_at": now()]])) docs") }
            catch { outcome = error }
        }
        metrics.finish(outcome)
    }
    func supply(_ module: String, metrics: Metrics, context: inout ErrorContext) throws {
        longSleep(0.2)
        let channel = try Channels.resolve(self, module: module)
        context.channel = try channel.destination as? String ?? json(channel.destination)
        if !channel.requiresSubmission {
            let sender = try self.sender(channel.destination, metrics: metrics)
            _ = try Channels.maintenance(self, module: module, sender: sender)
            return
        }
        for ranking in channel.ranking.map({ [$0] }) ?? ["hot", "new", "top"] {
            context.link = nil
            let reddit = try Reddit(config: config, metrics: metrics)
            let sender = try self.sender(channel.destination, metrics: metrics)
            var after: String?; var scanned = 0; var last: Supply?; var stop = false
            while scanned < channel.limit && !stop {
                var retries = 0; var page: Doc
                while true {
                    do { page = try reddit.listing(subreddit: channel.subreddit, ranking: ranking, limit: channel.limit, after: after); break }
                    catch {
                        retries += 1; if retries >= 10 { throw error }
                        metrics.count("reddit_listing_retries")
                        longSleep(2.818281828 * Double.pi / 2)
                    }
                }
                guard let items = object(page["data"])["children"] as? [Doc] else { throw R2TError.reddit }
                if items.isEmpty { break }
                for item in items {
                    if scanned >= channel.limit { break }; scanned += 1
                    let submission = object(item["data"]); let link = "https://redd.it/" + text(submission["id"])
                    context.link = link
                    if try sender.wasBefore(link) || sender.tooManyErrors(link) { continue }
                    let result = try Channels.post(self, module: module, channel: channel, submission: submission, sender: sender, reddit: reddit)
                    last = result
                    switch result {
                    case .sent: try sender.mark(link, sent: true); stop = true
                    case .reject: try sender.mark(link, sent: false)
                    case .skip: break
                    case .stop: stop = true
                    }
                    if stop { break }
                }
                after = object(page["data"])["after"] as? String
                if after == nil { break }
            }
            if last != nil { break }
        }
        context.link = nil
        try clean(config: config, channel: channel.destination as? String ?? "")
    }
}

func consumer(_ app: App) throws {
    guard app.config.workers > 0, app.config.maxPending > 0, app.config.batchSize > 0 else { throw R2TError.config }
    r2t_install_signals()
    let recovered = try app.db.update("tasks", ["status": ["$in": [2,5]], "updated_at": ["$lt": now() - 60]],
        ["$set": ["status": 1, "updated_at": now()]], multi: true)
    if recovered > 0 { log("Recovered \(recovered) abandoned tasks", warning: true) }
    log("Starting consumer Swift with \(app.config.workers) workers")
    let queue = OperationQueue(); queue.maxConcurrentOperationCount = app.config.workers
    // A single ownership scope drains submitted work after both signal stops
    // and database errors; no subsequent runtime may overlap these jobs.
    defer { log("Stopped claiming tasks; draining \(queue.operationCount) pending jobs"); queue.waitUntilAllOperationsAreFinished() }
    var nextMemory = 0.0
    while r2t_stopping() == 0 {
        if now() >= nextMemory {
            nextMemory = now() + 60
            if let status = try? String(contentsOfFile: "/proc/self/status", encoding: .utf8),
               let line = status.components(separatedBy: "\n").first(where: { $0.hasPrefix("VmRSS:") }),
               let kb = Double(line.split(whereSeparator: { $0.isWhitespace }).dropFirst().first ?? ""), kb >= 256 * 1024 {
                r2t_allocator(0, 1)
            }
        }
        let expired = try app.db.update("tasks", ["status": 1, "created_at": ["$lt": now() - 25 * 60]],
            ["$set": ["status": 4, "updated_at": now()]], multi: true)
        if expired > 0 { log("Failed \(expired) expired new tasks", warning: true) }
        let available = max(0, app.config.maxPending - queue.operationCount)
        let cutoff = now() - 25 * 60; var batch: [Doc] = []
        for _ in 0..<min(available, app.config.batchSize) {
            guard let task = try app.db.claim("tasks", ["status": 1, "created_at": ["$gte": cutoff]],
                ["$set": ["status": 5, "updated_at": now()]], sort: ["created_at": 1], projection: ["name": 1, "args": 1, "created_at": 1]) else { break }
            batch.append(task)
        }
        log("Claimed \(batch.count) new tasks")
        for task in batch { queue.addOperation { app.runJob(task) } }
        // One blocking wait, interrupted by the signal self-pipe, like the
        // reference's Event.wait(5). Avoid extra idle CPU from frequent wakes.
        r2t_wait_stop(5000)
    }
}

func schedules(_ config: Config) throws -> [(String, String)] {
    let data = try String(contentsOf: config.cronPath, encoding: .utf8)
    var result: [(String, String)] = []
    for line in data.components(separatedBy: .newlines).dropFirst() where !line.isEmpty {
        let fields = line.components(separatedBy: "\t")
        guard fields.count >= 2 else { throw R2TError.config }
        result.append((fields[0], fields[1]))
    }
    return result
}
func scheduler(_ app: App) throws {
    let current = Date(); var modules: [String] = []
    for (mask, module) in try schedules(app.config) {
        if try cronMatches(mask, date: current) { modules.append(module) }
    }
    modules.shuffle(); if modules.isEmpty { return }
    let created = now()
    let docs: [Doc] = modules.map { ["name": "supply", "args": ["submodule_name": $0, "config_filename": app.config.path.path],
        "status": 1, "created_at": created, "updated_at": created] }
    try app.db.insert("tasks", docs)
    if let run = activeRun(app.config.root) { emit(run, event: "scheduler_submitted", fields: ["submitted_jobs": docs.count]) }
    log("Inserted \(docs.count) tasks")
}
func cronMatches(_ mask: String, date: Date) throws -> Bool {
    let parts = mask.split(whereSeparator: { $0.isWhitespace }).map(String.init)
    guard parts.count == 5 else { throw R2TError.config }
    let calendar = Calendar(identifier: .gregorian)
    let values = calendar.dateComponents([.minute, .hour, .day, .month, .weekday], from: date)
    let minute = try cronField(parts[0], current: values.minute ?? 0, min: 0, max: 59)
    let hour = try cronField(parts[1], current: values.hour ?? 0, min: 0, max: 23)
    let day = try cronField(parts[2], current: values.day ?? 1, min: 1, max: 31)
    let month = try cronField(parts[3], current: values.month ?? 1, min: 1, max: 12)
    let weekday = try cronField(parts[4], current: (values.weekday ?? 1) - 1, min: 0, max: 7)
    let matchesDay = parts[2] != "*" && parts[4] != "*" ? day || weekday : day && weekday
    return minute && hour && month && matchesDay
}
func cronField(_ expression: String, current: Int, min minimum: Int, max maximum: Int) throws -> Bool {
    func parse(_ s: String) throws -> Int {
        if let i = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"].firstIndex(of: s.lowercased()) { return i }
        guard let n = Int(s) else { throw R2TError.config }; return n
    }
    var matches = false
    for item in expression.components(separatedBy: ",") {
        let split = item.components(separatedBy: "/"); guard split.count <= 2 else { throw R2TError.config }
        let range = split[0]; let step = try split.count == 2 ? parse(split[1]) : 1
        guard step > 0 else { throw R2TError.config }
        let first: Int; let last: Int
        if range == "*" { first = minimum; last = maximum }
        else {
            let bounds = range.components(separatedBy: "-"); guard bounds.count <= 2 else { throw R2TError.config }
            first = try parse(bounds[0]); last = try bounds.count == 2 ? parse(bounds[1]) : (split.count == 2 ? maximum : first)
        }
        guard first >= minimum, last <= maximum, first <= last else { throw R2TError.config }
        matches = matches || stride(from: first, through: last, by: step).contains { $0 == current || (maximum == 7 && $0 == 7 && current == 0) }
    }
    return matches
}
