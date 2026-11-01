#pragma once
#include "metrics.hpp"
namespace r2t {
struct Response {
    int status=0;std::string body;std::map<std::string,std::string> headers;bool too_large=false;std::string hash;
    Json json() const;
    bool ok() const{return status>=200&&status<300;}
};
class Http {
    std::shared_ptr<void> handle;
    bool telegram;
public:
    Metrics metrics;
    explicit Http(Metrics metrics={},bool telegram=false);
    Response request(const std::string &method,const std::string &url,const std::map<std::string,std::string> &headers={},const std::string &body="",const Json &multipart=nullptr,const Path &output={},uint64_t limit=0,const std::string &algorithm="",bool allow_initial_failure=false) const;
    bool download(const std::string &url,const Path &output,uint64_t limit) const;
    std::string metadata(const std::string &url) const;
    Json api(const std::string &token,const std::string &method,const Json &params,const Path &video={}) const;
};
std::string encode(const std::string &s);
std::string form(const std::map<std::string,std::string> &fields);
}
