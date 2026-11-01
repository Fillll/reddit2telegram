import Foundation
import Glibc

let mediaLimit: UInt64 = 50 * 1024 * 1024
protocol AckSink: AnyObject { func record(_ ids: [Int64]) throws }
struct Media {
    let kind: String
    let url: String
    var groups: [[Doc]] = []
}
func scalarCount(_ value: String) -> Int { value.unicodeScalars.count }
func scalarPrefix(_ value: String, _ count: Int) -> String { String(String.UnicodeScalarView(value.unicodeScalars.prefix(count))) }
func scalarDrop(_ value: String, _ count: Int) -> String { String(String.UnicodeScalarView(value.unicodeScalars.dropFirst(count))) }
func chunks<T>(_ values: [T], _ size: Int) -> [[T]] {
    stride(from: 0, to: values.count, by: size).map { Array(values[$0..<min($0 + size, values.count)]) }
}
func htmlDecode(_ value: String) -> String {
    var result = value
    // Reddit and Imgur media links contain escaped query separators. Numeric
    // entities are also decoded without changing URL percent escapes.
    if let regex = try? NSRegularExpression(pattern: "&#(x[0-9a-fA-F]+|[0-9]+);") {
        for match in regex.matches(in: result, range: NSRange(result.startIndex..., in: result)).reversed() {
            guard let range = Range(match.range(at: 1), in: result), let whole = Range(match.range, in: result) else { continue }
            let s = String(result[range]); let n = s.hasPrefix("x") ? UInt32(s.dropFirst(), radix: 16) : UInt32(s)
            if let n, let scalar = UnicodeScalar(n) { result.replaceSubrange(whole, with: String(scalar)) }
        }
    }
    for (a,b) in [("&quot;","\""),("&apos;","'"),("&lt;","<"),("&gt;",">"),("&nbsp;","\u{a0}"),("&amp;","&")] {
        result = result.replacingOccurrences(of: a, with: b)
    }
    return result
}
func splitMessage(_ body: String) -> (String, String) {
    let words = body.components(separatedBy: " ")
    if scalarCount(words[0]) > 4096 { return (scalarPrefix(body, 4096), scalarDrop(body, 4096)) }
    var size = 0; var take = 0
    for word in words {
        let n = scalarCount(word); if size + take + n > 4096 { break }
        size += n; take += 1
    }
    return (words.prefix(take).joined(separator: " "), words.dropFirst(take).joined(separator: " "))
}
func splitCaption(_ body: String) -> (String, String) {
    if scalarCount(body) <= 1024 { return (body, "") }
    var caption = ""; var tail = ""; var switched = false
    for word in body.components(separatedBy: CharacterSet(charactersIn: " \n")) {
        if !switched && scalarCount(caption) + scalarCount(word) + 1 < 1020 { caption += word + " " }
        else { switched = true; tail += " " + word }
    }
    return (caption + " ...", "... " + tail)
}
final class Sender {
    let config: Config
    let db: Database
    let destination: Any
    let http: HTTP
    let media: HTTP
    let videos: DispatchSemaphore
    let metrics: Metrics
    var acknowledgement: AckSink?
    init(config: Config, db: Database, destination: Any, metrics: Metrics, videos: DispatchSemaphore) throws {
        self.config = config; self.db = db; self.destination = destination; self.metrics = metrics; self.videos = videos
        http = try HTTP(metrics: metrics, telegram: true); media = try HTTP(metrics: metrics)
        shortSleep()
    }
    init(copy: Sender, destination: Any) {
        config = copy.config; db = copy.db; self.destination = destination
        http = copy.http; media = copy.media; videos = copy.videos; metrics = copy.metrics
    }
    var channel: String { destination as? String ?? ((try? json(destination)) ?? "") }
    @discardableResult func api(_ method: String, _ params: Doc = [:]) throws -> Any {
        var params = params
        if params["chat_id"] == nil && (method.hasPrefix("send") || method == "getChatMemberCount" || method == "getChatAdministrators") {
            params["chat_id"] = destination
        }
        let result = try http.api(token: text(object(config.values["telegram"])["token"]), method: method, params: params)
        if method.hasPrefix("send") || method == "forwardMessage" { try ack(result) }
        return result
    }
    func ack(_ result: Any) throws {
        guard let acknowledgement else { return }
        let items = result as? [Any] ?? [result]
        try acknowledgement.record(items.compactMap { item in
            guard object(item)["message_id"] is NSNumber else { return nil }
            return integer64(object(item)["message_id"])
        })
    }
    @discardableResult func sendText(_ body: String, preview: Bool = false, parse: String? = nil) throws -> Supply {
        var remaining = body; let split = scalarCount(body) >= 4096
        while true {
            let (part, next) = split ? splitMessage(remaining) : (remaining, "")
            var params: Doc = ["text": part, "disable_web_page_preview": preview]
            if let parse { params["parse_mode"] = parse }
            try api("sendMessage", params)
            if split { shortSleep() }
            if next.isEmpty { break }; remaining = next
        }
        return .sent
    }
    func sendImage(_ url: String, body: String) throws -> Supply {
        if scalarCount(body) > 1024 {
            log("Long pic in \(channel).")
            return try sendText("<a href=\"\(url)\">&#160;</a>" + body, parse: "HTML")
        }
        do { try api("sendPhoto", ["photo": url, "caption": body]); return .sent }
        catch let error as R2TError {
            switch error {
            case .rejected, .telegram, .network, .timeout, .forbidden, .rateLimit: return .skip
            default: throw error
            }
        }
    }
    func sendGIF(_ url: String, body: String) throws -> Supply {
        if urlSize(url) > mediaLimit { log("Too big."); return .reject }
        let (caption, tail) = splitCaption(body)
        do { try api("sendDocument", ["document": url, "caption": caption]) }
        catch R2TError.rejected { return .skip }
        if scalarCount(tail) > 1 { shortSleep(); try sendText(tail, preview: true) }
        return .sent
    }
    func sendGallery(_ groups: [[Doc]], body: String) throws -> Supply {
        try sendText(body); longSleep()
        for (index, group) in groups.enumerated() {
            do { try api("sendMediaGroup", ["media": group]); log("Successful gallery sent.") }
            catch { log("Gallery sent failed: \(safeError(error))", warning: true) }
            longSleep(Double(index + 2))
        }
        return .sent
    }
    func sendVideo(_ url: String, body: String, dash: String?) throws -> Supply {
        videos.wait(); defer { videos.signal() }
        let folder = config.app.appendingPathComponent("tmp/r2t-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let video = folder.appendingPathComponent("media.mp4")
        if !media.download(url, to: video, limit: mediaLimit) { return .reject }
        var send = video
        let base = url.split(separator: "/", omittingEmptySubsequences: false).dropLast().joined(separator: "/")
        let audioURL = dash.flatMap(dashAudio) ?? base + "/DASH_AUDIO_128.mp4"
        let audio = folder.appendingPathComponent("media.mp4.aac")
        if media.download(audioURL, to: audio, limit: mediaLimit) {
            let muxed = folder.appendingPathComponent("media.1.mp4")
            if mux(video: video, audio: audio, output: muxed) { send = muxed }
        }
        let size = (try FileManager.default.attributesOfItem(atPath: send.path)[.size] as? NSNumber)?.uint64Value ?? 0
        if size == 0 || size > mediaLimit { return .reject }
        let (caption, tail) = splitCaption(body)
        let result = try http.api(token: text(object(config.values["telegram"])["token"]), method: "sendVideo",
            params: ["chat_id": destination, "caption": caption], video: send)
        try ack(result)
        if scalarCount(tail) > 1 { shortSleep(); try sendText(tail, preview: true) }
        return .sent
    }
    private func mux(video: URL, audio: URL, output: URL) -> Bool {
        let paths = (ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin").components(separatedBy: ":")
        guard let binary = paths.map({ URL(fileURLWithPath: $0).appendingPathComponent("ffmpeg") }).first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else { return false }
        let process = Process(); process.executableURL = binary
        process.arguments = ["-hide_banner", "-loglevel", "error", "-y", "-threads", "1", "-i", video.path,
            "-threads", "1", "-i", audio.path, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", output.path]
        process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
        let completed = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in completed.signal() }
        do { try process.run() } catch { return false }
        if completed.wait(timeout: .now() + 60) == .timedOut {
            kill(process.processIdentifier, SIGKILL); process.waitUntilExit(); return false
        }
        process.waitUntilExit()
        let bytes = (try? FileManager.default.attributesOfItem(atPath: output.path)[.size] as? NSNumber)?.uint64Value ?? 0
        return process.terminationStatus == 0 && bytes > 0
    }
    private func dashAudio(_ url: String) -> String? {
        guard let body = try? media.metadata(url), let regex = try? NSRegularExpression(pattern: "<BaseURL>([^<]+)</BaseURL>") else { return nil }
        let candidates = regex.matches(in: body, range: NSRange(body.startIndex..., in: body)).compactMap { match -> String? in
            guard let range = Range(match.range(at: 1), in: body) else { return nil }; return String(body[range])
        }.filter { $0.uppercased().contains("AUDIO") }
        guard let last = candidates.last, let range = url.range(of: "DASHPlaylist.mpd") else { return nil }
        let query = url.firstIndex(of: "?").map { String(url[$0...]) } ?? ""
        return String(url[..<range.lowerBound]) + last + query
    }
    func urlSize(_ url: String) -> UInt64 {
        guard let response = try? media.request("HEAD", url) else { return 0 }
        return UInt64(response.headers["content-length"] ?? "") ?? 0
    }
    func wasBefore(_ url: String) throws -> Bool {
        let id = url.components(separatedBy: "/").last ?? url
        for filter: Doc in [["channel": channel.lowercased(), "url_id": id],
            ["channel": channel.lowercased(), "url": url.lowercased()],
            ["channel": channel.lowercased(), "url": ["$regex": NSRegularExpression.escapedPattern(for: id)]]] {
            if !(try db.find("urls", filter, limit: 1, projection: ["_id": 1])).isEmpty {
                metrics.count("previously_seen_candidates"); return true
            }
        }
        return false
    }
    func tooManyErrors(_ url: String) throws -> Bool {
        guard let record = try db.one("errors", ["channel": channel.lowercased(), "url": url.lowercased()]) else { return false }
        return number(record["cnt"]) >= 2
    }
    func mark(_ url: String, sent: Bool) throws {
        try db.insert("urls", [["url_id": url.components(separatedBy: "/").last ?? url, "url": url.lowercased(),
            "ts": dateBSON(), "channel": channel.lowercased(), "sent": sent]])
        metrics.post(channel: channel, url: url, sent: sent)
    }
    func duplicate(_ url: String) throws -> Bool {
        guard let response = try? media.request("GET", url, limit: mediaLimit, digest: "MD5"),
              (200..<300).contains(response.status), !response.tooLarge, let hash = response.digest else { return false }
        let filter: Doc = ["channel": channel.lowercased(), "md5_sum": hash]
        // Return the pre-update document in a single atomic operation.
        let result = try db.command("findAndModify", "contents", ["query": filter,
            "update": ["$setOnInsert": ["channel": channel.lowercased(), "md5_sum": hash, "ts": dateBSON()]], "upsert": true, "new": false])
        let seen = result["value"] is Doc
        if seen { log("Duplicated found!"); metrics.count("duplicate_media_candidates") }
        return seen
    }
    func classify(_ submission: Doc) throws -> Media {
        let url = text(submission["url"])
        guard let parsed = URL(string: url), let host = parsed.host else { throw R2TError.media }
        let lower = url.lowercased()
        if let items = object(submission["gallery_data"])["items"] as? [Doc] {
            let numeric = items.allSatisfy { $0["id"] is NSNumber }
            let strings = items.allSatisfy { $0["id"] is String }
            guard numeric || strings else { throw R2TError.media }
            var last: [String: Doc] = [:]
            for item in items { last[idString(item["id"])] = item }
            let ordered = last.values.sorted { numeric ? integer64($0["id"]) < integer64($1["id"]) : text($0["id"]) < text($1["id"]) }
            var mediaItems: [Doc] = []
            for item in ordered {
                let source = object(object(object(submission["media_metadata"])[text(item["media_id"])])["s"])
                guard let link = source["u"] as? String ?? source["mp4"] as? String else { throw R2TError.media }
                let decoded = htmlDecode(link); let parsed = URL(string: decoded)
                let normalized = parsed?.host == "preview.redd.it" ? "https://i.redd.it" + (parsed?.path ?? "") : decoded.replacingOccurrences(of: "auto=webp", with: "auto=jpg")
                mediaItems.append(["type": source["u"] is String ? "photo" : "video", "media": normalized])
            }
            return Media(kind: "gallery", url: "", groups: chunks(mediaItems, 10))
        }
        var video = truth(submission["is_video"]) ? object(object(submission["media"])["reddit_video"]) : [:]
        if video.isEmpty, let cross = array(submission["crosspost_parent_list"]).first, truth(object(cross)["is_video"]) {
            video = object(object(object(cross)["media"])["reddit_video"])
        }
        if !video.isEmpty { return Media(kind: truth(video["is_gif"]) ? "gif" : "video", url: text(video["fallback_url"])) }
        if truth(submission["is_self"]) { return Media(kind: "text", url: "") }
        if host == "i.redd.it" && [".jpg", ".jpeg", ".png"].contains(where: lower.hasSuffix) { return Media(kind: "img", url: url) }
        if ["i.imgur.com", "i.stack.imgur.com"].contains(host) {
            if lower.hasSuffix(".gifv") { return Media(kind: "gif", url: String(url.dropLast(5)) + ".mp4") }
            if lower.hasSuffix(".gif") || lower.hasSuffix(".mp4") { return Media(kind: "gif", url: url) }
            if [".jpg", ".jpeg", ".png"].contains(where: lower.hasSuffix) { return Media(kind: "img", url: url) }
        }
        let mime = (try? media.request("HEAD", url).headers["content-type"]) ?? ""
        if ["image/jpeg", "image/png"].contains(mime) { return Media(kind: "img", url: url) }
        if mime.contains("image/gif") {
            if url.hasSuffix(".gif") {
                let mp4 = String(url.dropLast(4)) + ".mp4"
                if (try? media.request("HEAD", mp4).headers["content-type"]) == "video/mp4" { return Media(kind: "gif", url: mp4) }
            }
            return Media(kind: "gif", url: url)
        }
        if url.hasSuffix(".gifv") {
            let mp4 = String(url.dropLast(5)) + ".mp4"
            if (try? media.request("HEAD", mp4).headers["content-type"]) == "video/mp4" { return Media(kind: "gif", url: mp4) }
            let gif = String(url.dropLast())
            if (try? media.request("HEAD", gif).headers["content-type"]) == "image/gif" { return Media(kind: "gif", url: gif) }
        }
        if ["imgur.com", "www.imgur.com", "m.imgur.com"].contains(host) { return try imgur(url, parsed: parsed) }
        if host.contains("gfycat.com") {
            let parts = parsed.path.split(separator: "/").map(String.init)
            let name = parts.first == "detail" ? parts.dropFirst().first : parts.first
            if let name, let content = try? media.metadata("https://api.gfycat.com/v1/gfycats/" + name),
               let data = try? parseJSON(Data(content.utf8)), let link = object(object(data)["gfyItem"])["mp4Url"] as? String {
                return Media(kind: "gif", url: link)
            }
        }
        return Media(kind: "other", url: url)
    }
    private func imgur(_ url: String, parsed: URL) throws -> Media {
        var config = object(self.config.values["imgur"])
        if config.isEmpty { config = (try? Config(path: self.config.app.appendingPathComponent("configs/imgur.yml").path).values) ?? [:] }
        if config.isEmpty { return Media(kind: "other", url: url) }
        let parts = parsed.path.split(separator: "/").map(String.init)
        guard let first = parts.first, first != "topic" else { return Media(kind: "other", url: url) }
        let album = ["a", "gallery"].contains(first)
        let identifier = album ? parts.dropFirst().first ?? "" : parts.last ?? ""
        let id = identifier.components(separatedBy: ".")[0]
        func image(_ value: Doc) -> Doc {
            let animated = truth(value["animated"])
            var link = text(value["link"])
            if animated { link = [text(value["mp4"]), text(value["gifv"]), link].first(where: { !$0.isEmpty }) ?? "" }
            if link.hasSuffix(".gifv") { link = String(link.dropLast()) }
            return ["type": animated ? "video" : "photo", "media": link]
        }
        for endpoint in album ? ["album", "image"] : ["image"] {
            if endpoint == "image" && first == "a" { break }
            guard let response = try? media.request("GET", "https://api.imgur.com/3/\(endpoint)/\(id)",
                headers: ["Authorization": "Client-ID " + text(config["client_id"])]),
                  let body = try? response.json(), truth(object(body)["success"]) else { continue }
            let data = object(object(body)["data"])
            if let images = data["images"] as? [Doc] { return Media(kind: "album", url: url, groups: chunks(images.map(image), 10)) }
            return Media(kind: truth(data["animated"]) ? "gif" : "img", url: text(image(data)["media"]))
        }
        return Media(kind: "other", url: url)
    }
    func simple(_ initial: Doc, options: Doc = [:], reddit: Reddit) throws -> Supply {
        var submission = initial
        if options["min_upvotes_limit"] is NSNumber && submission["score"] == nil { submission = try reddit.hydrate(submission) }
        if options["min_upvotes_limit"] is NSNumber && number(submission["score"]) < number(options["min_upvotes_limit"]) { return .skip }
        let missing = submission["url"] == nil || submission["is_self"] == nil
            || (truth(submission["is_gallery"]) && submission["gallery_data"] == nil)
            || (object(submission["gallery_data"])["items"] is [Any] && submission["media_metadata"] == nil)
            || (truth(submission["is_video"]) && submission["media"] == nil)
        let mediaInfo: Media
        do {
            if missing { submission = try reddit.hydrate(submission) }
            mediaInfo = try classify(submission)
        } catch { log("HTTP fail prevented at \(channel)"); return .skip }
        if ["title", "selftext", "score", "subreddit", "over_18"].contains(where: { submission[$0] == nil }) { submission = try reddit.hydrate(submission) }
        let score = Int(number(submission["score"]))
        if truth(options["nsfw_filter_out"] ?? true) && truth(submission["over_18"]) { return .reject }
        if truth(options["check_dups"]) && !mediaInfo.url.isEmpty {
            if try duplicate(mediaInfo.url) { return .reject }
        }
        let rule = options[mediaInfo.kind] ?? true
        if !truth(rule) { return .reject }
        var fields = ["what": mediaInfo.kind, "url": mediaInfo.url, "title": text(submission["title"]),
            "self_text": text(submission["selftext"]), "link": text(submission["url"]), "short_link": "https://redd.it/" + text(submission["id"]),
            "subreddit_name": text(submission["subreddit"]), "score": String(score), "upvotes": human(score), "channel": channel]
        for (key, value) in options { fields[key] = try value as? String ?? json(value) }
        let fallback: String
        switch mediaInfo.kind {
        case "text": fallback = "{title}\n\n{self_text}\n\n{short_link}\n{channel}"
        case "video", "gallery": fallback = "{title}\n\n{short_link}\n{channel}"
        case "album", "other": fallback = "{title}\n{link}\n\n{short_link}\n{channel}"
        default: fallback = "{title}\n{short_link}\n{channel}"
        }
        let template = rule as? String ?? fallback
        if mediaInfo.kind == "text" {
            if options["max_selftext_len"] is NSNumber { fields["self_text"] = scalarPrefix(text(submission["selftext"]), Int(number(options["max_selftext_len"]))) + "..." }
            let preview = truth(options["disable_web_page_preview"])
            let markdown = try format(template.replacingOccurrences(of: "{short_link}", with: "[{short_link}]({short_link})").replacingOccurrences(of: "{channel}", with: "[{channel}]({channel})"), fields)
            do { return try sendText(markdown, preview: preview, parse: "Markdown") }
            catch R2TError.rejected { log("Markdown fail in \(channel); sending as plain text."); return try sendText(format(template, fields), preview: preview) }
        }
        let body = try format(template, fields)
        switch mediaInfo.kind {
        case "img": return try sendImage(mediaInfo.url, body: body)
        case "gif": return try sendGIF(mediaInfo.url, body: body)
        case "video": return try sendVideo(mediaInfo.url, body: body, dash: object(object(submission["media"])["reddit_video"])["dash_url"] as? String)
        case "gallery", "album": return try sendGallery(mediaInfo.groups, body: body)
        default: return try sendText(body)
        }
    }
}
@discardableResult func clean(config: Config, channel: String? = nil) throws -> UInt64 {
    longSleep(1 / (Double.pi * exp(1)))
    let folder = config.app.appendingPathComponent("tmp")
    let entries = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey])
    var deleted: UInt64 = 0
    for path in entries {
        let props = try path.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        if props.isRegularFile != true || path.lastPathComponent == "empty.md" { continue }
        if let channel, !path.lastPathComponent.contains(String(channel.dropFirst())) { continue }
        do { try FileManager.default.removeItem(at: path); deleted += UInt64(props.fileSize ?? 0) } catch { continue }
    }
    return deleted
}
