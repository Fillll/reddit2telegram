#include "sender.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
static bool spawn_process(const char *const *args, int output, pid_t *pid, Error *error) {
    posix_spawn_file_actions_t actions;
    REQUIRE(!posix_spawn_file_actions_init(&actions), E_IO, false);
    posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
    if (output < 0)
        posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
    else
        posix_spawn_file_actions_adddup2(&actions, output, STDOUT_FILENO);
    int code = posix_spawnp(pid, args[0], &actions, NULL, (char *const *)args, environ);
    posix_spawn_file_actions_destroy(&actions);
    REQUIRE(!code, E_IO, false);
    return true;
}
char *command_output(const char *const *args, Error *error) {
    int fd[2];
    REQUIRE(!pipe2(fd, O_CLOEXEC), E_IO, NULL);
    pid_t pid;
    if (!spawn_process(args, fd[1], &pid, error)) {
        close(fd[0]);
        close(fd[1]);
        return NULL;
    }
    close(fd[1]);
    BUF(out);
    char bytes[8192];
    bool failed = false;
    for (;;) {
        ssize_t n = read(fd[0], bytes, sizeof(bytes));
        if (n > 0)
            buffer_add(&out, bytes, (size_t)n);
        else if (n == 0)
            break;
        else if (errno != EINTR) {
            failed = true;
            break;
        }
    }
    close(fd[0]);
    int status = 0;
    pid_t waited;
    do {
        waited = waitpid(pid, &status, 0);
    } while (waited < 0 && errno == EINTR);
    REQUIRE(!failed && waited == pid && WIFEXITED(status) && !WEXITSTATUS(status), E_IO, NULL);
    return buffer_take(&out);
}
bool mux_video(const char *video, const char *audio, const char *output) {
    const char *args[] = {"ffmpeg", "-hide_banner", "-loglevel", "error",    "-y",    "-threads",
                          "1",      "-i",           video,       "-threads", "1",     "-i",
                          audio,    "-map",         "0:v:0",     "-map",     "1:a:0", "-c",
                          "copy",   output,         NULL};
    Error error = {0};
    pid_t pid;
    if (!spawn_process(args, -1, &pid, &error))
        return false;
    double deadline = monotonic_now() + 60;
    int status = 0;
    while (monotonic_now() < deadline) {
        pid_t waited = waitpid(pid, &status, WNOHANG);
        if (waited == pid) {
            struct stat st;
            return WIFEXITED(status) && !WEXITSTATUS(status) && !stat(output, &st) &&
                   st.st_size > 0;
        }
        if (waited < 0 && errno != EINTR)
            return false;
        pause_between(.05, .05);
    }
    kill(pid, SIGKILL);
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
    return false;
}
