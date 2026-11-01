#include "model.hpp"
#include "build_info.hpp"
#include <iostream>
namespace r2t { inline constexpr bool full_port_complete=false; }
int main(int argc,char **argv){
    using namespace r2t;
    try{
        std::vector<std::string> args(argv+1,argv+argc);
        if(std::find(args.begin(),args.end(),"--describe")!=args.end()){
            r2t_init();std::cout<<Json({{"language","cpp"},{"version",build::version},{"compiler",build::compiler},{"source_commit",build::commit},{"full_port_complete",full_port_complete},{"profile","Release -O3 -DNDEBUG; LTO"},{"standard","C++23"},{"json_library","nlohmann/json 3.12.0"},{"mongodb_client",r2t_mongoc_version()},{"http_client",r2t_curl_version()},{"configuration_sha256",{{"local_channels",digest(build::local_channels)},{"weighted_channel",digest(build::weighted_channel)},{"milestones",digest(build::milestones)}}}}).dump()<<'\n';return 0;
        }
        if(std::find(args.begin(),args.end(),"--version")!=args.end()){std::cout<<"r2t-cpp "<<build::version<<'\n';return 0;}
        if(!full_port_complete)throw Error(Kind::IncompletePort);
        throw Error(Kind::UnknownTask);
    }catch(...){auto error=safe_error();log(std::string("r2t-cpp: ")+error.what(),true);return 1;}
}
