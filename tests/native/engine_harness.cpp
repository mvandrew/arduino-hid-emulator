#include "../../arduino/hid_emulator/Engine.h"
#include "../../arduino/hid_emulator/HoldGuard.h"
#include <vector>
#include <string>

static std::string output;
static std::vector<unsigned> reports;
static hidv1::Io io=hidv1::SENT;
static bool writable=true;
static hidv1::Io keyboard(uint8_t mask,uint8_t usage) {
  if(io==hidv1::SENT) reports.push_back((unsigned(mask)<<8)|usage);
  return io;
}
static bool emit(const char* data,size_t count) {
  if(!writable) return false;
  output.append(data,count); return true;
}
static hidv1::Engine* engine=nullptr;
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif
API void reset_engine() {
  delete engine; output.clear(); reports.clear(); io=hidv1::SENT; writable=true;
  engine=new hidv1::Engine(keyboard,emit); engine->tick(0);
  output.clear(); reports.clear();
}
API void feed_engine(const char* bytes,unsigned now) {
  while(*bytes) engine->feed(*bytes++,now);
}
API void tick_engine(unsigned now,int connected) { engine->tick(now,connected!=0); }
API const char* get_output() { return output.c_str(); }
API void clear_output() { output.clear(); }
API unsigned report_count() { return unsigned(reports.size()); }
API unsigned report_at(unsigned index) { return reports.at(index); }
API void set_io(int value) { io=hidv1::Io(value); }
API void set_writable(int value) { writable=value!=0; }
API int is_armed() { return engine->armed(); }
API int is_held() { return engine->held(); }
static hidv1::HoldGuard guard;
API void guard_commit(int nonzero) { guard.committed(nonzero!=0); }
API int guard_tick() { return guard.tick(); }
