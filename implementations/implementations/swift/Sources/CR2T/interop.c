#include "CR2T.h"
#include <bson/bson.h>
#include <mongoc/mongoc.h>
#include <curl/curl.h>
#include <yaml.h>
#include <openssl/evp.h>
#include <pthread.h>
#include <malloc.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <time.h>

static pthread_once_t once = PTHREAD_ONCE_INIT;
static volatile sig_atomic_t stopping = 0;
static void stop(int sig) { (void)sig; stopping = 1; }
/* Driver messages can include connection strings. Swift reports only safe
 * categories and codes, never arbitrary transport error text. */
static void quiet_log(mongoc_log_level_t level, const char *domain,
                      const char *message, void *unused) {
    (void)level; (void)domain; (void)message; (void)unused;
}
static void initialize(void) {
    mongoc_init();
    mongoc_log_set_handler(quiet_log, NULL);
    curl_global_init(CURL_GLOBAL_DEFAULT);
}
void r2t_init(void) { pthread_once(&once, initialize); }
void r2t_free(void *p) { bson_free(p); }
void r2t_allocator(int arenas, int trim) {
    if (arenas > 0) mallopt(M_ARENA_MAX, arenas);
    if (trim) malloc_trim(0);
}
void r2t_install_signals(void) {
    struct sigaction action = {0}; action.sa_handler = stop;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL); sigaction(SIGINT, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
}
int r2t_stopping(void) { return stopping; }
const char *r2t_mongoc_version(void) { return mongoc_get_version(); }
const char *r2t_curl_version(void) { return curl_version(); }

void *r2t_db_open(const char *uri_string) {
    r2t_init(); bson_error_t error;
    mongoc_uri_t *uri = mongoc_uri_new_with_error(uri_string, &error);
    if (!uri) return NULL;
    mongoc_client_pool_t *pool = mongoc_client_pool_new(uri);
    mongoc_uri_destroy(uri);
    if (pool) mongoc_client_pool_set_error_api(pool, 2);
    return pool;
}
void r2t_db_close(void *pool) { if (pool) mongoc_client_pool_destroy(pool); }
char *r2t_db_command(void *pool, const char *name, const char *json, int *code) {
    *code = 0; bson_error_t error = {0};
    bson_t *command = bson_new_from_json((const uint8_t *)json, -1, &error);
    if (!command) { *code = -1; return NULL; }
    mongoc_client_t *client = mongoc_client_pool_pop(pool);
    if (!client) { bson_destroy(command); *code = -2; return NULL; }
    mongoc_database_t *db = mongoc_client_get_database(client, name);
    bson_t reply;
    bool ok = mongoc_database_command_with_opts(db, command, NULL, NULL, &reply, &error);
    char *result = bson_as_relaxed_extended_json(&reply, NULL);
    if (!ok) *code = error.code ? (int)error.code : -3;
    bson_destroy(&reply); bson_destroy(command); mongoc_database_destroy(db);
    mongoc_client_pool_push(pool, client);
    return result;
}

static bool yaml_value(yaml_document_t *doc, int index, bson_t *out, const char *key, int depth) {
    if (depth > 64) return false;
    yaml_node_t *node = yaml_document_get_node(doc, index);
    if (!node) return false;
    if (node->type == YAML_MAPPING_NODE) {
        bson_t child; if (!bson_append_document_begin(out, key, -1, &child)) return false;
        for (yaml_node_pair_t *p = node->data.mapping.pairs.start; p < node->data.mapping.pairs.top; ++p) {
            yaml_node_t *k = yaml_document_get_node(doc, p->key);
            if (!k || k->type != YAML_SCALAR_NODE ||
                !yaml_value(doc, p->value, &child, (char *)k->data.scalar.value, depth + 1)) return false;
        }
        return bson_append_document_end(out, &child);
    }
    if (node->type == YAML_SEQUENCE_NODE) {
        bson_t child; if (!bson_append_array_begin(out, key, -1, &child)) return false;
        unsigned i = 0;
        for (yaml_node_item_t *p = node->data.sequence.items.start; p < node->data.sequence.items.top; ++p) {
            char field[32]; snprintf(field, sizeof(field), "%u", i++);
            if (!yaml_value(doc, *p, &child, field, depth + 1)) return false;
        }
        return bson_append_array_end(out, &child);
    }
    if (node->type != YAML_SCALAR_NODE) return false;
    const char *v = (const char *)node->data.scalar.value;
    if (node->data.scalar.style == YAML_PLAIN_SCALAR_STYLE) {
        if (!strcmp(v, "null") || !strcmp(v, "Null") || !strcmp(v, "NULL") || !strcmp(v, "~") || !*v)
            return bson_append_null(out, key, -1);
        if (!strcasecmp(v,"true") || !strcasecmp(v,"yes") || !strcasecmp(v,"on")) return bson_append_bool(out,key,-1,true);
        if (!strcasecmp(v,"false") || !strcasecmp(v,"no") || !strcasecmp(v,"off")) return bson_append_bool(out,key,-1,false);
        char *end = NULL; errno = 0;
        long long n = strtoll(v, &end, 10);
        if (!errno && end != v && !*end) return bson_append_int64(out,key,-1,n);
        errno = 0; double d = strtod(v,&end);
        if (!errno && end != v && !*end) return bson_append_double(out,key,-1,d);
    }
    return bson_append_utf8(out,key,-1,v,(int)node->data.scalar.length);
}
char *r2t_yaml_json(const char *path) {
    FILE *file = fopen(path,"rb"); if (!file) return NULL;
    yaml_parser_t parser; yaml_document_t doc;
    if (!yaml_parser_initialize(&parser)) { fclose(file); return NULL; }
    yaml_parser_set_input_file(&parser,file);
    int ok = yaml_parser_load(&parser,&doc); yaml_parser_delete(&parser); fclose(file);
    if (!ok) return NULL;
    bson_t wrapper; bson_init(&wrapper);
    ok = yaml_value(&doc,1,&wrapper,"value",0); yaml_document_delete(&doc);
    char *result = ok ? bson_as_relaxed_extended_json(&wrapper,NULL) : NULL;
    bson_destroy(&wrapper); return result;
}
char *r2t_digest(const char *algorithm, const void *bytes, size_t length) {
    const EVP_MD *md = EVP_get_digestbyname(algorithm); if (!md) return NULL;
    unsigned char digest[EVP_MAX_MD_SIZE]; unsigned n = 0;
    if (!EVP_Digest(bytes,length,digest,&n,md,NULL)) return NULL;
    char *result = bson_malloc(n*2+1);
    for (unsigned i=0;i<n;i++) snprintf(result+i*2,3,"%02x",digest[i]);
    return result;
}

typedef struct {
    r2t_response *response; FILE *file; uint64_t maximum;
    double last_progress; curl_off_t last_download, last_upload;
    long idle_seconds;
    EVP_MD_CTX *digest;
} transfer;
static double monotonic_now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9;
}
static size_t receive(char *bytes, size_t size, size_t count, void *data) {
    transfer *t=data; size_t n=size*count;
    t->last_progress=monotonic_now(); t->response->received+=n;
    if (t->maximum && t->response->received>t->maximum) { t->response->too_large=1; return 0; }
    if (t->response->too_large) return 0;
    if (t->digest) return EVP_DigestUpdate(t->digest,bytes,n) ? n : 0;
    if (t->file) return fwrite(bytes,1,n,t->file);
    if (SIZE_MAX-t->response->length<=n) return 0;
    unsigned char *new_body=realloc(t->response->body,t->response->length+n+1);
    if (!new_body) return 0;
    t->response->body=new_body;
    memcpy(new_body+t->response->length,bytes,n);
    t->response->length+=n; new_body[t->response->length]=0; return n;
}
static size_t header(char *bytes,size_t size,size_t count,void *data) {
    transfer *t=data; size_t n=size*count;
    if (t->maximum && n>15 && !strncasecmp(bytes,"Content-Length:",15)) {
        unsigned long long length=strtoull(bytes+15,NULL,10);
        if(length>t->maximum) t->response->too_large=1;
    }
    if (n>=5 && !memcmp(bytes,"HTTP/",5)) {
        free(t->response->headers); t->response->headers=NULL;
        /* Count each real response, including redirects, excluding 100 Continue. */
        const char *space=memchr(bytes,' ',n); long status=space ? strtol(space+1,NULL,10) : 0;
        if (status>=200) {
            t->response->requests++;
            if(status>=400) t->response->http_errors++;
            if(status==429) t->response->rate_limits++;
        }
    }
    size_t used=t->response->headers ? strlen(t->response->headers) : 0;
    if (used+n>128*1024) return 0;
    char *p=realloc(t->response->headers,used+n+1); if (!p) return 0;
    t->response->headers=p; memcpy(p+used,bytes,n); p[used+n]=0;
    t->last_progress=monotonic_now(); return n;
}
static int progress(void *data,curl_off_t total,curl_off_t downloaded,curl_off_t up_total,curl_off_t uploaded) {
    (void)total; (void)up_total; transfer *t=data;
    if (downloaded!=t->last_download || uploaded!=t->last_upload) t->last_progress=monotonic_now();
    t->last_download=downloaded; t->last_upload=uploaded;
    return monotonic_now()-t->last_progress>t->idle_seconds;
}
static const char *bson_string(const bson_t *doc,const char *key) {
    bson_iter_t i; return bson_iter_init_find(&i,doc,key) && BSON_ITER_HOLDS_UTF8(&i) ? bson_iter_utf8(&i,NULL) : "";
}
static int multipart_load(CURL *curl, const char *json, curl_mime **mime) {
    bson_error_t error; bson_t *doc=bson_new_from_json((uint8_t*)json,-1,&error); if (!doc) return 0;
    *mime=curl_mime_init(curl); bson_iter_t outer;
    if (!*mime) { bson_destroy(doc); return 0; }
    if (bson_iter_init_find(&outer,doc,"fields") && BSON_ITER_HOLDS_DOCUMENT(&outer)) {
        bson_iter_t fields; bson_iter_recurse(&outer,&fields);
        while (bson_iter_next(&fields)) {
            if (!BSON_ITER_HOLDS_UTF8(&fields)) { bson_destroy(doc); return 0; }
            curl_mimepart *part=curl_mime_addpart(*mime);
            curl_mime_name(part,bson_iter_key(&fields));
            curl_mime_data(part,bson_iter_utf8(&fields,NULL),CURL_ZERO_TERMINATED);
        }
    }
    if (bson_iter_init_find(&outer,doc,"files") && BSON_ITER_HOLDS_DOCUMENT(&outer)) {
        bson_iter_t files; bson_iter_recurse(&outer,&files);
        while (bson_iter_next(&files)) {
            if (!BSON_ITER_HOLDS_DOCUMENT(&files)) { bson_destroy(doc); return 0; }
            uint32_t n; const uint8_t *raw; bson_iter_document(&files,&n,&raw); bson_t spec; bson_init_static(&spec,raw,n);
            curl_mimepart *part=curl_mime_addpart(*mime);
            curl_mime_name(part,bson_iter_key(&files));
            if (curl_mime_filedata(part,bson_string(&spec,"path"))!=CURLE_OK) { bson_destroy(doc); return 0; }
            curl_mime_filename(part,bson_string(&spec,"filename"));
            curl_mime_type(part,bson_string(&spec,"content_type"));
        }
    }
    bson_destroy(doc); return 1;
}
void *r2t_http_open(void) { r2t_init(); return curl_easy_init(); }
void r2t_http_close(void *client) { if(client) curl_easy_cleanup(client); }
r2t_response *r2t_http_request(void *client,const char *method,const char *url,const char *headers,
    const void *body,size_t body_length,const char *multipart,const char *output_path,uint64_t maximum,
    long connect_seconds,long read_seconds,int redirects,const char *digest_algorithm) {
    r2t_response *r=calloc(1,sizeof(*r)); if (!r) return NULL;
    CURL *curl=client; if (!curl) { r->error=CURLE_FAILED_INIT; return r; }
    curl_easy_reset(curl);
    transfer t={.response=r,.maximum=maximum,.last_progress=monotonic_now(),.idle_seconds=read_seconds};
    if (digest_algorithm) {
        const EVP_MD *md=EVP_get_digestbyname(digest_algorithm);
        t.digest=EVP_MD_CTX_new();
        if(!md || !t.digest || !EVP_DigestInit_ex(t.digest,md,NULL)) {
            EVP_MD_CTX_free(t.digest); r->error=CURLE_FAILED_INIT; return r;
        }
    }
    if (output_path && *output_path) { t.file=fopen(output_path,"wb"); if (!t.file) { EVP_MD_CTX_free(t.digest); r->error=CURLE_WRITE_ERROR; return r; } }
    curl_easy_setopt(curl,CURLOPT_URL,url);
    curl_easy_setopt(curl,CURLOPT_NOSIGNAL,1L);
    curl_easy_setopt(curl,CURLOPT_CONNECTTIMEOUT,connect_seconds);
    curl_easy_setopt(curl,CURLOPT_NOPROGRESS,0L);
    curl_easy_setopt(curl,CURLOPT_XFERINFOFUNCTION,progress);
    curl_easy_setopt(curl,CURLOPT_XFERINFODATA,&t);
    curl_easy_setopt(curl,CURLOPT_WRITEFUNCTION,receive);
    curl_easy_setopt(curl,CURLOPT_WRITEDATA,&t);
    curl_easy_setopt(curl,CURLOPT_HEADERFUNCTION,header);
    curl_easy_setopt(curl,CURLOPT_HEADERDATA,&t);
    curl_easy_setopt(curl,CURLOPT_ACCEPT_ENCODING,"");
    curl_easy_setopt(curl,CURLOPT_FOLLOWLOCATION,(long)redirects);
    curl_easy_setopt(curl,CURLOPT_MAXREDIRS,30L);
    curl_easy_setopt(curl,CURLOPT_HTTP_VERSION,CURL_HTTP_VERSION_1_1);
    curl_easy_setopt(curl,CURLOPT_PROTOCOLS_STR,"http,https");
    curl_easy_setopt(curl,CURLOPT_REDIR_PROTOCOLS_STR,"http,https");
    struct curl_slist *list=NULL;
    char *copy=strdup(headers ? headers : ""),*save=NULL;
    for(char *line=strtok_r(copy,"\n",&save);line;line=strtok_r(NULL,"\n",&save)) list=curl_slist_append(list,line);
    /* Match HTTPX: avoid the otherwise implicit 100-Continue round trip. */
    list=curl_slist_append(list,"Expect:"); curl_easy_setopt(curl,CURLOPT_HTTPHEADER,list);
    curl_mime *mime=NULL;
    if (!strcmp(method,"HEAD")) curl_easy_setopt(curl,CURLOPT_NOBODY,1L);
    else if (multipart) {
        if (!multipart_load(curl,multipart,&mime)) { r->error=CURLE_BAD_FUNCTION_ARGUMENT; goto finish; }
        curl_easy_setopt(curl,CURLOPT_MIMEPOST,mime);
    } else if (!strcmp(method,"POST")) {
        curl_easy_setopt(curl,CURLOPT_POST,1L); curl_easy_setopt(curl,CURLOPT_POSTFIELDS,body ? body : "");
        curl_easy_setopt(curl,CURLOPT_POSTFIELDSIZE_LARGE,(curl_off_t)body_length);
    } else curl_easy_setopt(curl,CURLOPT_CUSTOMREQUEST,method);
    r->error=curl_easy_perform(curl);
    curl_easy_getinfo(curl,CURLINFO_RESPONSE_CODE,&r->status);
    curl_off_t sent=0; curl_easy_getinfo(curl,CURLINFO_SIZE_UPLOAD_T,&sent); r->sent=sent>0 ? (uint64_t)sent : 0;
finish:
    if(t.digest) {
        unsigned char bytes[EVP_MAX_MD_SIZE]; unsigned n=0;
        if(!r->error && EVP_DigestFinal_ex(t.digest,bytes,&n)) {
            r->body_digest=malloc(n*2+1);
            if(r->body_digest) for(unsigned i=0;i<n;i++) snprintf(r->body_digest+i*2,3,"%02x",bytes[i]);
        }
        EVP_MD_CTX_free(t.digest);
    }
    curl_mime_free(mime); curl_slist_free_all(list); free(copy);
    if(t.file) fclose(t.file);
    return r;
}
void r2t_response_free(r2t_response *r) {
    if(r) { free(r->body); free(r->headers); free(r->body_digest); free(r); }
}
