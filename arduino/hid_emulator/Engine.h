// HID v1 protocol/state machine, shared verbatim by AVR and native fault tests.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

namespace hidv1 {
enum Io { SENT, WOULD_BLOCK, IO_FAILED };
enum Status { DONE, REJECTED, UNKNOWN, ACCEPTED };
enum Code { OK, READY, ALIVE, CANCELLED, RELEASED, BAD_ARGUMENT, BUSY,
  STALE_GENERATION, BAD_SESSION, UNSUPPORTED_VERSION, UNSUPPORTED_USAGE,
  STALE_ID, SESSION_CONFLICT, CANCELLED_BEFORE_DOWN, UNKNOWN_COMMAND, IO_UNCERTAIN };
enum Verb { HELLO, HB, BEGIN, TAP, DOWN, UP, CANCEL, RELEASE, CLOSE, CHORD, INVALID };
inline const char* statusName(Status s) {
  static const char* const names[] = {"DONE", "REJECTED", "UNKNOWN", "ACCEPTED"};
  return names[s];
}
inline const char* codeName(Code c) {
  static const char* const names[] = {"OK","READY","ALIVE","CANCELLED","RELEASED",
    "BAD_ARGUMENT","BUSY","STALE_GENERATION","BAD_SESSION","UNSUPPORTED_VERSION",
    "UNSUPPORTED_USAGE","STALE_ID","SESSION_CONFLICT","CANCELLED_BEFORE_DOWN",
    "UNKNOWN_COMMAND","IO_UNCERTAIN"};
  return names[c];
}
inline uint16_t crc16(const char* data, size_t size) {
  uint16_t crc = 0xFFFF;
  while (size--) {
    crc ^= uint16_t(uint8_t(*data++)) << 8;
    for (uint8_t i=0; i<8; ++i) crc = (crc & 0x8000) ? (crc<<1)^0x1021 : crc<<1;
  }
  return crc;
}
struct Command {
  uint32_t id, gen, fingerprint;
  Verb verb;
  uint8_t usage, mask, hold, lead, tail;
};
struct Cached { Command cmd; Status status; Code code; bool valid; };

class Engine {
 public:
  typedef Io (*Keyboard)(uint8_t, uint8_t);
  typedef bool (*Output)(const char*, size_t);
  Engine(Keyboard keyboard, Output output) : keyboard_(keyboard), output_(output) {
    memset(cache_, 0, sizeof(cache_));
    session_[0]=0;
  }

  void feed(char ch, uint32_t now) {
    if (used_ && uint32_t(now-frameAt_)>=100) { used_=0; discard_=true; }
    if (ch=='\n') {
      if (!discard_ && used_) { rx_[used_]=0; parse(now); }
      used_=0; discard_=false;
      return;
    }
    if (discard_) return;
    if (uint8_t(ch)<33 || uint8_t(ch)>126) {
      if (ch!=' ') { discard_=true; used_=0; return; }
    }
    if (!used_) frameAt_=now;
    if (used_>=127) { discard_=true; used_=0; return; }
    rx_[used_++]=ch;
  }

  void tick(uint32_t now, bool connected=true) {
    if (used_ && uint32_t(now-frameAt_)>=100) { used_=0; discard_=true; }
    if (!connected || (session_[0] && uint32_t(now-heartbeatAt_)>=1000)) disconnect();
    if(active_ && op_.verb==CHORD && uint32_t(now-opAt_)>=100) {
      finishOp(UNKNOWN,IO_UNCERTAIN); failSession();
    }
    if (active_ && phase_==0) {
      Io io=keyboard_(op_.mask, op_.verb==CHORD?0:op_.usage);
      if (io==SENT) {
        held_=true; holdAt_=now; phase_=1;
        if (op_.verb==DOWN) finishOp(DONE, OK);
      } else if (io==IO_FAILED || uint32_t(now-opAt_)>=20) {
        finishOp(UNKNOWN, IO_UNCERTAIN); failSession();
      }
    }
    if(active_ && op_.verb==CHORD && !releaseNeeded_) {
      if((phase_==1 && uint32_t(now-holdAt_)>=op_.lead) ||
         (phase_==3 && uint32_t(now-holdAt_)>=op_.hold)) {
        Io io=keyboard_(op_.mask,phase_==1?op_.usage:0);
        if(io==SENT) { phase_=phase_==1?3:4; holdAt_=now; }
        else if(io==IO_FAILED) { finishOp(UNKNOWN,IO_UNCERTAIN); failSession(); }
      }
      if(active_ && phase_==4 && uint32_t(now-holdAt_)>=op_.tail) releaseNeeded_=true;
    }
    if (active_ && op_.verb!=CHORD && phase_==1 && uint32_t(now-holdAt_)>=op_.hold) releaseNeeded_=true;
    if (held_ && !active_ && uint32_t(now-holdAt_)>=100) releaseNeeded_=true;
    if (active_ && phase_==2) releaseNeeded_=true;
    if (releaseNeeded_) {
      Io io=keyboard_(0,0);
      if (io==SENT) {
        held_=false; releaseNeeded_=false;
        if (active_) {
          bool beforeKey=op_.verb==CHORD && phase_==1;
          finishOp(beforeKey?REJECTED:DONE,beforeKey?CANCELLED_BEFORE_DOWN:OK);
        }
        if (control_) {
          Command cmd=controlCmd_; control_=false;
          terminal(cmd,DONE,cmd.verb==CANCEL ? CANCELLED : cmd.verb==RELEASE ? RELEASED : OK);
          if (cmd.verb==CLOSE) clearSession();
        }
      } else {
        if (!releaseTiming_) { releaseAt_=now; releaseTiming_=true; }
        if (io==IO_FAILED || uint32_t(now-releaseAt_)>=20) {
          if (active_) finishOp(UNKNOWN,IO_UNCERTAIN);
          if (control_) { Command cmd=controlCmd_; control_=false; terminal(cmd,UNKNOWN,IO_UNCERTAIN); }
          // Continue trying zero reports, even after an uncertain session closes.
          failSession();
        }
      }
    }
    if (!releaseNeeded_) releaseTiming_=false;
  }

  void disconnect() {
    // No queued down survives USB/DTR loss or lease expiry. Zero report retried.
    active_=false; control_=false; current_=0; held_=false;
    releaseNeeded_=true; clearSession();
    used_=0; discard_=false;
  }
  bool armed() const { return current_!=0; }
  bool held() const { return held_; }
  bool sessionOpen() const { return session_[0]!=0; }

 private:
  Keyboard keyboard_;
  Output output_;
  char rx_[128],session_[17];
  uint8_t used_=0, cacheNext_=0,phase_=0;
  bool discard_=false, active_=false, held_=false, control_=false;
  bool releaseNeeded_=true, releaseTiming_=false;
  uint32_t frameAt_=0, heartbeatAt_=0, highId_=0, fence_=0, current_=0;
  uint32_t opAt_=0,holdAt_=0,releaseAt_=0;
  Command op_={},controlCmd_={};
  Cached cache_[4];

  void clearSession() {
    session_[0]=0; highId_=0; fence_=0; current_=0;
    memset(cache_,0,sizeof(cache_)); cacheNext_=0;
  }
  void failSession() { active_=false; control_=false; clearSession(); releaseNeeded_=true; }
  bool reply(const Command& cmd, Status status, Code code, const char* sid=0) {
    char out[128];
    int n=snprintf(out,sizeof(out),"R1 %s %lu %lu %s %s%s",sid?sid:session_,
      (unsigned long)cmd.id,(unsigned long)cmd.gen,statusName(status),codeName(code),
      code==READY ? " 1 1.1.0 0000007F 128 0 1000 100" : "");
    if(n<0 || n+7>=int(sizeof(out))) { failSession(); return false; }
    uint16_t crc=crc16(out,n);
    int tail=snprintf(out+n,sizeof(out)-n," *%04X\n",unsigned(crc));
    if (!output_(out,n+tail)) { failSession(); return false; }
    return true;
  }
  void terminal(const Command& cmd, Status status, Code code) {
    Cached& entry=cache_[cacheNext_];
    entry.cmd=cmd; entry.status=status; entry.code=code; entry.valid=true;
    cacheNext_=(cacheNext_+1)%4;
    reply(cmd,status,code);
  }
  void finishOp(Status status,Code code) {
    Command cmd=op_; active_=false;
    terminal(cmd,status,code);
  }
  static bool decimal(const char* token,uint32_t& value) {
    if(!token[0] || (token[0]=='0' && token[1])) return false;
    value=0;
    for(const char* p=token;*p;++p) {
      if(*p<'0'||*p>'9') return false;
      uint8_t digit=*p-'0';
      if(value>429496729UL || (value==429496729UL && digit>5)) return false;
      value=value*10+digit;
    }
    return true;
  }
  static bool hex(const char* s,uint8_t size,uint32_t* out=0) {
    if(strlen(s)!=size) return false;
    uint32_t value=0; bool nonzero=false;
    for(uint8_t i=0;i<size;++i) {
      char c=s[i];
      if(!((c>='0'&&c<='9')||(c>='A'&&c<='F'))) return false;
      uint8_t digit=c<='9'?c-'0':c-'A'+10;
      value=(value<<4)|digit; if(digit) nonzero=true;
    }
    if(out) *out=value;
    return size!=16 || nonzero;
  }
  void parse(uint32_t now) {
    // Remove checksum after verification; split only canonical single spaces.
    char* star=strrchr(rx_,'*'); uint32_t supplied;
    if(!star||star==rx_||star[-1]!=' '||!hex(star+1,4,&supplied)) return;
    size_t bodySize=star-rx_-1;
    if(crc16(rx_,bodySize)!=supplied) return;
    uint32_t fingerprint=2166136261UL;
    for(size_t i=0;i<bodySize;++i) fingerprint=(fingerprint^uint8_t(rx_[i]))*16777619UL;
    star[-1]=0;
    char* fields[11]; uint8_t count=0; char* p=rx_;
    if(!*p) return;
    while(true) {
      if(count==11 || *p==' ') return;
      fields[count++]=p;
      char* space=strchr(p,' ');
      if(!space) break;
      *space=0; p=space+1;
      if(!*p) return;
    }
    if(count<5 || strcmp(fields[0],"Q1") || !hex(fields[1],16)) return;
    Command cmd={}; cmd.fingerprint=fingerprint;
    if(!decimal(fields[2],cmd.id)||!cmd.id||!decimal(fields[3],cmd.gen)) return;
    static const char* const verbs[]={"HELLO","HB","BEGIN","TAP","DOWN","UP","CANCEL","RELEASE","CLOSE","CHORD"};
    cmd.verb=INVALID;
    for(uint8_t i=0;i<10;++i) if(!strcmp(fields[4],verbs[i])) cmd.verb=Verb(i);
    if(cmd.verb==HELLO && !session_[0]) {
      if(count!=6 || cmd.gen!=0) { reply(cmd,REJECTED,BAD_ARGUMENT,fields[1]); return; }
      if(strcmp(fields[5],"1")) { reply(cmd,REJECTED,UNSUPPORTED_VERSION,fields[1]); return; }
      if(held_||active_||releaseNeeded_) { reply(cmd,REJECTED,BUSY,fields[1]); return; }
      strcpy(session_,fields[1]); heartbeatAt_=now; highId_=cmd.id;
      terminal(cmd,DONE,READY); return;
    }
    if(!session_[0] || strcmp(fields[1],session_)) { reply(cmd,REJECTED,BAD_SESSION,fields[1]); return; }
    if(active_&&op_.id==cmd.id) {
      if(op_.fingerprint!=cmd.fingerprint) conflict(cmd);
      else reply(cmd,ACCEPTED,OK);
      return;
    }
    if(control_&&controlCmd_.id==cmd.id) {
      if(controlCmd_.fingerprint!=cmd.fingerprint) conflict(cmd);
      else reply(cmd,ACCEPTED,OK);
      return;
    }
    for(uint8_t i=0;i<4;++i) if(cache_[i].valid && cache_[i].cmd.id==cmd.id) {
      if(cache_[i].cmd.fingerprint!=cmd.fingerprint) conflict(cmd);
      else reply(cmd,cache_[i].status,cache_[i].code);
      return;
    }
    if(cmd.id<=highId_) { reply(cmd,REJECTED,STALE_ID); return; }
    highId_=cmd.id;
    uint8_t expected=cmd.verb==CHORD?10:cmd.verb==TAP?8:cmd.verb==DOWN?7:cmd.verb==HELLO?6:5;
    if(count!=expected) { terminal(cmd,REJECTED,BAD_ARGUMENT); return; }
    if(cmd.verb==INVALID) { terminal(cmd,REJECTED,UNKNOWN_COMMAND); return; }
    bool global=cmd.verb==HELLO||cmd.verb==HB||cmd.verb==RELEASE||cmd.verb==CLOSE;
    if((global && cmd.gen!=0)||(!global && cmd.gen==0)) { terminal(cmd,REJECTED,BAD_ARGUMENT); return; }
    if(cmd.verb==HELLO) { terminal(cmd,REJECTED,BUSY); return; }
    if(cmd.verb==HB) { heartbeatAt_=now; terminal(cmd,DONE,ALIVE); return; }
    if(cmd.verb==BEGIN) {
      if(cmd.gen<=fence_) { terminal(cmd,REJECTED,STALE_GENERATION); return; }
      if(current_||active_||control_||held_||releaseNeeded_) { terminal(cmd,REJECTED,BUSY); return; }
      current_=cmd.gen; fence_=cmd.gen; terminal(cmd,DONE,OK); return;
    }
    if(cmd.verb==CANCEL||cmd.verb==RELEASE||cmd.verb==CLOSE) {
      if(control_) { terminal(cmd,REJECTED,BUSY); return; }
      if(cmd.verb==CANCEL) {
        if(cmd.gen>fence_) fence_=cmd.gen;
        if(current_>cmd.gen) { terminal(cmd,DONE,CANCELLED); return; }
      }
      if(current_>fence_) fence_=current_;
      current_=0;
      if(active_&&phase_==0) finishOp(REJECTED,CANCELLED_BEFORE_DOWN);
      controlCmd_=cmd; control_=true; releaseNeeded_=true;
      return;
    }
    if(cmd.gen!=current_ || !current_) { terminal(cmd,REJECTED,STALE_GENERATION); return; }
    if(active_||control_||releaseNeeded_) { terminal(cmd,REJECTED,BUSY); return; }
    if(cmd.verb==UP) {
      op_=cmd; active_=true; phase_=2; opAt_=now; releaseNeeded_=true; return;
    }
    if(held_) { terminal(cmd,REJECTED,BUSY); return; }
    uint32_t usage,mask,hold=100;
    if(!decimal(fields[5],usage)||!decimal(fields[6],mask)||mask>255||
      (cmd.verb==TAP && (!decimal(fields[7],hold)||hold<1||hold>100))) {
      terminal(cmd,REJECTED,BAD_ARGUMENT); return;
    }
    if(usage<4||usage>115) { terminal(cmd,REJECTED,UNSUPPORTED_USAGE); return; }
    if(cmd.verb==CHORD) {
      uint32_t lead,tail;
      if(!mask || !decimal(fields[7],lead)||!decimal(fields[8],hold)||!decimal(fields[9],tail)||
         lead<1||hold<1||tail<1||lead>90||hold>90||tail>90||lead+hold+tail>90) {
        terminal(cmd,REJECTED,BAD_ARGUMENT); return;
      }
      cmd.lead=lead; cmd.tail=tail;
    }
    cmd.usage=usage; cmd.mask=mask; cmd.hold=hold;
    op_=cmd; active_=true; phase_=0; opAt_=now;
    reply(cmd,ACCEPTED,OK);
  }
  void conflict(const Command& cmd) {
    reply(cmd,REJECTED,SESSION_CONFLICT);
    active_=false; control_=false; failSession();
  }
};
} // namespace hidv1
