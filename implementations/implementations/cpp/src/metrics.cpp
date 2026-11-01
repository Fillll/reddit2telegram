#include "metrics.hpp"
#include <fcntl.h>
#include <unistd.h>
namespace r2t {
std::optional<Json> active_run(const Path &root) {
    try {
        auto run = parse(read_file(root / "implementations/benchmarks/state/active.json"));
        if (number(get(run, "started_at"), INFINITY) <= now() &&
            now() < number(get(run, "deadline")))
            return run;
    } catch (...) {
    }
    return {};
}
void emit(const Json &run, const std::string &event, Json fields) {
    if (now() < number(get(run, "started_at"), INFINITY) || now() >= number(get(run, "deadline")))
        return;
    fields["schema"] = 1;
    fields["run_id"] = get(run, "run_id");
    fields["ts"] = now();
    fields["event"] = event;
    auto path = text(run, "events_path");
    int fd = open(path.c_str(), O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0)
        return;
    auto line = fields.dump() + "\n";
    auto n = write(fd, line.data(), line.size());
    close(fd);
    if (n != static_cast<ssize_t>(line.size()))
        log("benchmark event write failed", true);
}
Metrics::Metrics(const Path &root, const std::string &task, const std::string &module,
                 std::optional<double> created) {
    auto run = active_run(root);
    if (!run)
        return;
    state = std::make_shared<State>();
    state->run = *run;
    state->task_id = task;
    state->module = module;
    state->wait = created ? Json(std::max(0., now() - *created)) : Json(nullptr);
    emit(*run, "job_start",
         {{"task_id", task}, {"module", module}, {"queue_wait_seconds", state->wait}});
}
void Metrics::count(const std::string &key, uint64_t n) const {
    if (state) {
        std::lock_guard guard(state->lock);
        state->counters[key] += n;
    }
}
void Metrics::finish(const std::optional<Error> &error) const {
    if (!state)
        return;
    std::lock_guard guard(state->lock);
    emit(
        state->run, "job_end",
        {{"task_id", state->task_id},
         {"module", state->module},
         {"status", error ? "failed" : "success"},
         {"error_type", error ? Json(error->what()) : Json(nullptr)},
         {"duration_seconds",
          std::chrono::duration<double>(std::chrono::steady_clock::now() - state->started).count()},
         {"queue_wait_seconds", state->wait},
         {"counters", state->counters}});
}
void Metrics::post(const std::string &channel, const std::string &url, bool sent) const {
    count(sent ? "posts_recorded_sent" : "candidates_rejected");
    if (sent && state)
        emit(state->run, "post_record",
             {{"task_id", state->task_id},
              {"post_key", digest(lower(channel) + std::string(1, '\0') + lower(url))}});
}
void Metrics::delivery(const Json &result) const {
    auto messages = result.is_array() ? result : Json::array({result});
    for (auto &message : messages) {
        if (get(message, "message_id").is_null())
            continue;
        count("telegram_messages");
        std::string kind = "text_or_other";
        for (auto key : {"video", "animation", "photo", "document", "audio"})
            if (!get(message, key).is_null()) {
                kind = key;
                break;
            }
        count("telegram_messages_" + kind);
    }
}
} // namespace r2t
