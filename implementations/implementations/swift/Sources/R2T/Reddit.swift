import Foundation

final class Reddit {
    let http: HTTP
    let config: Config
    private var token: String?
    private var expiry = 0.0
    private var next = 0.0
    init(config: Config, metrics: Metrics) throws {
        self.config = config; http = try HTTP(metrics: metrics)
    }
    private func authorize() throws {
        if token != nil && now() < expiry { return }
        let c = object(config.values["reddit"])
        let basic = Data((text(c["client_id"]) + ":" + text(c["client_secret"])).utf8).base64EncodedString()
        let response = try http.request("POST", "https://www.reddit.com/api/v1/access_token",
            headers: ["User-Agent": text(c["user_agent"]), "Authorization": "Basic " + basic,
                "Content-Type": "application/x-www-form-urlencoded"],
            body: formBody(["grant_type": "password", "username": text(c["username"]), "password": text(c["password"])]))
        guard (200..<300).contains(response.status) else { throw R2TError.reddit }
        let data = object(try response.json())
        guard let token = data["access_token"] as? String else { throw R2TError.reddit }
        self.token = token; expiry = now() + number(data["expires_in"], 3600) - 10
    }
    private func feedback(_ response: HTTPResponse) {
        if let remaining = Double(response.headers["x-ratelimit-remaining"] ?? ""),
           let reset = Double(response.headers["x-ratelimit-reset"] ?? ""),
           let used = Double(response.headers["x-ratelimit-used"] ?? "") {
            if remaining <= 0 { next = now() + reset }
            else { next = now() + min(reset, min(10, max(0, reset - (600 - 600 / (remaining + used) * used)))) }
        }
    }
    func get(_ path: String, params: [String: String] = [:]) throws -> Any {
        var params = params; params["raw_json"] = "1"
        let query = String(decoding: formBody(params), as: UTF8.self)
        for attempt in 0..<3 {
            if attempt > 0 { pause(attempt == 1 ? 0 : 2, attempt == 1 ? 2 : 4) }
            if next > now() { Thread.sleep(forTimeInterval: next - now()) }
            try authorize()
            let response: HTTPResponse
            do {
                response = try http.request("GET", "https://oauth.reddit.com\(path)?\(query)",
                    headers: ["User-Agent": text(object(config.values["reddit"])["user_agent"]), "Authorization": "Bearer " + (token ?? "")])
            } catch {
                if attempt == 2 { throw error }; continue
            }
            feedback(response)
            if response.status == 401 { token = nil; expiry = 0; if attempt < 2 { continue } }
            if [408,500,502,503,504,520,522].contains(response.status) && attempt < 2 { continue }
            guard response.status < 400 else { throw R2TError.reddit }
            return try response.json()
        }
        throw R2TError.reddit
    }
    func listing(subreddit: String, ranking: String, limit: Int, after: String?) throws -> Doc {
        var fields = ["limit": String(min(25, limit))]
        if let after { fields["after"] = after }
        if ranking == "top" { fields["t"] = "all" }
        return object(try get("/r/\(subreddit)/\(ranking)", params: fields))
    }
    func hydrate(_ submission: Doc) throws -> Doc {
        let id = text(submission["id"]); guard !id.isEmpty else { throw R2TError.reddit }
        let response = array(try get("/comments/\(id)", params: ["limit": "2048", "sort": "confidence"]))
        let children = array(object(object(response.first)["data"])["children"])
        guard let result = object(children.first)["data"] as? Doc else { throw R2TError.reddit }
        return result
    }
}
