// A tiny countdown shared by the interrupt-level guard and native tests.
#pragma once
#include <stdint.h>
namespace hidv1 {
class HoldGuard {
 public:
  void committed(bool nonzero) {
    if(!nonzero) { held_=false; remaining_=0; }
    else if(!held_) { held_=true; remaining_=100; }
    // Intermediate chord reports never extend continuous modifier hold.
  }
  bool tick() {
    if(!held_) return false;
    if(remaining_) --remaining_;
    return remaining_==0; // retry zero every tick if endpoint was not writable
  }
 private:
  volatile uint8_t remaining_=0;
  volatile bool held_=false;
};
}
