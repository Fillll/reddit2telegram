#include "sender.hpp"
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
extern char **environ;
namespace r2t {
static pid_t spawn(const std::vector<std::string> &args, int output) {
    if (args.empty())
        throw Error(Kind::Io);
    std::vector<char *> argv;
    for (auto &arg : args)
        argv.push_back(const_cast<char *>(arg.c_str()));
    argv.push_back(nullptr);
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    ScopeExit destroy([&] { posix_spawn_file_actions_destroy(&actions); });
    posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
    if (output < 0)
        posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
    else
        posix_spawn_file_actions_adddup2(&actions, output, STDOUT_FILENO);
    pid_t pid;
    if (posix_spawnp(&pid, argv[0], &actions, nullptr, argv.data(), environ) != 0)
        throw Error(Kind::Io);
    return pid;
}
std::string command_output(const std::vector<std::string> &args) {
    int pipefd[2];
    if (pipe2(pipefd, O_CLOEXEC) < 0)
        throw Error(Kind::Io);
    ScopeExit release([&] {
        close(pipefd[0]);
        close(pipefd[1]);
    });
    auto pid = spawn(args, pipefd[1]);
    close(pipefd[1]);
    pipefd[1] = -1;
    std::string out;
    char bytes[8192];
    ssize_t n;
    while ((n = read(pipefd[0], bytes, sizeof(bytes))) > 0)
        out.append(bytes, n);
    int status = 0;
    while (waitpid(pid, &status, 0) < 0)
        if (errno != EINTR)
            throw Error(Kind::Io);
    if (!WIFEXITED(status) || WEXITSTATUS(status))
        throw Error(Kind::Io);
    return out;
}
bool mux(const Path &video, const Path &audio, const Path &output) {
    pid_t pid;
    try {
        pid = spawn({"ffmpeg", "-hide_banner", "-loglevel", "error", "-y",   "-threads",     "1",
                     "-i",     video.string(), "-threads",  "1",     "-i",   audio.string(), "-map",
                     "0:v:0",  "-map",         "1:a:0",     "-c",    "copy", output.string()},
                    -1);
    } catch (...) {
        return false;
    }
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
    int status = 0;
    while (std::chrono::steady_clock::now() < deadline) {
        auto result = waitpid(pid, &status, WNOHANG);
        if (result == pid) {
            std::error_code error;
            auto bytes = std::filesystem::file_size(output, error);
            return WIFEXITED(status) && !WEXITSTATUS(status) && !error && bytes > 0;
        }
        if (result < 0 && errno != EINTR)
            return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    kill(pid, SIGKILL);
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
    return false;
}
} // namespace r2t
