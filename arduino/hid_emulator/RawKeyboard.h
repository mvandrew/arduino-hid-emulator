// Leonardo / ATmega32U4 + Arduino AVR core 1.8.8 only.
// One complete 8-byte report committed atomically; never calls blocking USB_Send.
#pragma once
#include <Arduino.h>
#include <HID.h>
#include <avr/interrupt.h>
#include "Engine.h"
#include "HoldGuard.h"

#if !defined(__AVR_ATmega32U4__)
#error "HID v1 raw endpoint implementation requires ATmega32U4"
#endif
#if F_CPU != 16000000UL
#error "Timer3 hold guard requires the validated 16MHz Leonardo profile"
#endif

class RawKeyboard : public PluggableUSBModule {
 public:
  RawKeyboard() : PluggableUSBModule(1,1,epType_) {
    epType_[0]=EP_TYPE_INTERRUPT_IN;
    memset(report_,0,sizeof(report_));
    PluggableUSB().plug(this);
  }
  hidv1::Io send(uint8_t mask,uint8_t usage) {
    if(!USBDevice.configured() || USBDevice.isSuspended()) return hidv1::IO_FAILED;
    uint8_t state=SREG; cli();
    uint8_t previous=UENUM; UENUM=pluggedEndpoint;
    // No writes until a complete report fits in a writable bank. No other code
    // owns this endpoint, and interrupts stay disabled for exactly eight bytes.
    if(!(UEINTX & _BV(RWAL)) || UEBCLX>USB_EP_SIZE-8) {
      UENUM=previous; SREG=state; return hidv1::WOULD_BLOCK;
    }
    uint8_t data[8]={mask,0,usage,0,0,0,0,0};
    for(uint8_t i=0;i<8;++i) UEDATX=data[i];
    UEINTX=0x3A; // AVR core ReleaseTX(): clear TXINI/FIFOCON, commit bank.
    // Commit report/guard state while still atomic with respect to Timer3.
    memcpy(report_,data,8);
    guard_.committed(mask || usage);
    UENUM=previous; SREG=state;
    return hidv1::SENT;
  }
  void safetyTick() {
    // No Engine/serial calls or waiting in the ISR. A stalled main loop cannot
    // keep a key down until the WDT reset (Windows can retain keys over reset).
    if(guard_.tick()) send(0,0);
  }
 protected:
  int getInterface(uint8_t* count) override {
    ++*count;
    HIDDescriptor desc={
      D_INTERFACE(pluggedInterface,1,USB_DEVICE_CLASS_HUMAN_INTERFACE,HID_SUBCLASS_NONE,HID_PROTOCOL_NONE),
      D_HIDREPORT(sizeof(descriptor_)),
      D_ENDPOINT(USB_ENDPOINT_IN(pluggedEndpoint),USB_ENDPOINT_TYPE_INTERRUPT,USB_EP_SIZE,1)
    };
    return USB_SendControl(0,&desc,sizeof(desc));
  }
  int getDescriptor(USBSetup& s) override {
    if(s.bmRequestType!=REQUEST_DEVICETOHOST_STANDARD_INTERFACE ||
       s.wValueH!=HID_REPORT_DESCRIPTOR_TYPE || s.wIndex!=pluggedInterface) return 0;
    return USB_SendControl(TRANSFER_PGM,descriptor_,sizeof(descriptor_));
  }
  bool setup(USBSetup& s) override {
    if(s.wIndex!=pluggedInterface) return false;
    if(s.bmRequestType==REQUEST_DEVICETOHOST_CLASS_INTERFACE) {
      if(s.bRequest==HID_GET_REPORT) return USB_SendControl(0,report_,8)>=0;
      if(s.bRequest==HID_GET_IDLE) return USB_SendControl(0,&idle_,1)>=0;
      if(s.bRequest==HID_GET_PROTOCOL) return USB_SendControl(0,&protocol_,1)>=0;
    }
    if(s.bmRequestType==REQUEST_HOSTTODEVICE_CLASS_INTERFACE) {
      if(s.bRequest==HID_SET_IDLE) { idle_=s.wValueH; return true; }
      if(s.bRequest==HID_SET_PROTOCOL) { protocol_=s.wValueL; return true; }
    }
    return false;
  }
  // Preserve the baseline USB serial string so Windows retains its COM mapping.
  uint8_t getShortName(char* name) override { memcpy(name,"HIDFG",5); return 5; }
 private:
  uint8_t epType_[1],report_[8],idle_=0,protocol_=1;
  hidv1::HoldGuard guard_;
  static const uint8_t descriptor_[43] PROGMEM;
};
const uint8_t RawKeyboard::descriptor_[43] PROGMEM={
  0x05,0x01,0x09,0x06,0xA1,0x01, // desktop keyboard collection
  0x05,0x07,0x19,0xE0,0x29,0xE7,0x15,0x00,0x25,0x01,
  0x75,0x01,0x95,0x08,0x81,0x02, // eight modifier bits
  0x95,0x01,0x75,0x08,0x81,0x03, // reserved byte
  0x95,0x06,0x75,0x08,0x15,0x00,0x25,0x73,0x19,0x00,0x29,0x73,
  0x81,0x00,0xC0
};
