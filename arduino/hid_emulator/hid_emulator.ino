// HID v1, Leonardo/ATmega32U4, AVR core 1.8.8. No automatic legacy fallback.
#include <Arduino.h>
#include <avr/wdt.h>
#include "Engine.h"
#include "RawKeyboard.h"

void earlyWatchdogOff() __attribute__((naked, section(".init3"), used));
void earlyWatchdogOff() { MCUSR=0; wdt_disable(); }
RawKeyboard keyboard;
static char tx[512];
static uint16_t head=0,tail=0;
hidv1::Io sendKeyboard(uint8_t mask,uint8_t usage) { return keyboard.send(mask,usage); }
bool queueReply(const char* bytes,size_t count) {
  uint16_t free=(tail-head-1)&511;
  if(count>free) return false;
  for(size_t i=0;i<count;++i) { tx[head]=bytes[i]; head=(head+1)&511; }
  return true;
}
hidv1::Engine engine(sendKeyboard,queueReply);
ISR(TIMER3_COMPA_vect) { keyboard.safetyTick(); }
void setup() {
  Serial.begin(115200);
  // Reserve Timer3: 16MHz / 64 / 250 = 1kHz, independent of the main loop.
  uint8_t state=SREG; cli();
  TCCR3A=0; TCCR3B=_BV(WGM32)|_BV(CS31)|_BV(CS30);
  TCNT3=0; OCR3A=249; TIMSK3=_BV(OCIE3A);
  SREG=state;
  wdt_enable(WDTO_2S);
}
void loop() {
  // AVR CDC uses a 120ms WDT reset for Leonardo's 1200-baud bootloader touch.
  // Feeding our application WDT here would prevent that reset indefinitely.
  const uint8_t prescalerMask=_BV(WDP3)|_BV(WDP2)|_BV(WDP1)|_BV(WDP0);
  if(Serial.baud()==1200 && !Serial.dtr() && (WDTCSR & _BV(WDE)) &&
     (WDTCSR & prescalerMask)==WDTO_120MS) {
    head=tail=0;
    engine.tick(millis(),false);
    return; // do not feed CDC reset; resume safely if core cancels the touch
  }
  wdt_reset();
  uint32_t now=millis();
  bool connected=USBDevice.configured() && Serial.dtr() && !USBDevice.isSuspended();
  if(!connected) { head=tail=0; engine.tick(now,false); return; }
  engine.tick(now);
  uint8_t budget=128;
  while(budget-- && Serial.available()) {
    char ch=char(Serial.read());
#ifdef HIDV1_FAULT_INJECTION
    // Test image only: an out-of-band byte freezes loop to exercise AVR WDT.
    // Never compiled into the production image. Interrupts stay enabled.
    if(ch=='!') { while(true) {} }
#endif
    engine.feed(ch,millis());
  }
  engine.tick(millis());
  int room=Serial.availableForWrite();
  while(room-- > 0 && head!=tail) {
    // Only this loop owns CDC_TX; availableForWrite guarantees byte capacity.
    if(Serial.write(uint8_t(tx[tail]))!=1) { engine.disconnect(); head=tail=0; break; }
    tail=(tail+1)&511;
  }
}
