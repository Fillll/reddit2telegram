#pragma once
#include "model.hpp"
namespace r2t {
std::optional<Json> active_run(const Path &root);
void emit(const Json &run,const std::string &event,Json fields);
class Metrics {
    struct State {
        Json run;std::string task_id,module;Json wait;
        std::chrono::steady_clock::time_point started=std::chrono::steady_clock::now();
        std::map<std::string,uint64_t> counters;std::mutex lock;
    };
    std::shared_ptr<State> state;
public:
    Metrics()=default;
    Metrics(const Path &root,const std::string &task,const std::string &module,std::optional<double> created);
    void count(const std::string &key,uint64_t n=1) const;
    void finish(const std::optional<Error> &error) const;
    void post(const std::string &channel,const std::string &url,bool sent) const;
    void delivery(const Json &result) const;
};
}
