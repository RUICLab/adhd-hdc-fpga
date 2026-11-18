#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_cpu.h"
#include "esp_system.h"
#include "hdc_packed.h"
#if HDC_CLASSES==10
#include "vectors_k10.h"
#define FIXTURE(C,S) k10_case##C##_##S
#elif HDC_CLASSES==26
#include "vectors_k26.h"
#define FIXTURE(C,S) k26_case##C##_##S
#else
#error HDC_CLASSES must be 10 or 26
#endif
static hdc_context ctx;
static uint32_t model[HDC_DIM],query[HDC_QUERY_WORDS];
static uint8_t features[HDC_FEATURES];
static uint16_t scores[HDC_CLASSES];
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static const uint32_t *const models[]={FIXTURE(0,model),FIXTURE(1,model),FIXTURE(2,model),FIXTURE(3,model)};
static const uint32_t *const queries[]={FIXTURE(0,query),FIXTURE(1,query),FIXTURE(2,query),FIXTURE(3,query)};
static const uint8_t *const inputs[]={FIXTURE(0,features),FIXTURE(1,features),FIXTURE(2,features),FIXTURE(3,features)};
static const uint16_t *const expected[]={FIXTURE(0,scores),FIXTURE(1,scores),FIXTURE(2,scores),FIXTURE(3,scores)};
static void load(unsigned c){memcpy(model,models[c],sizeof(model));memcpy(features,inputs[c],sizeof(features));}
static int matches(unsigned c,unsigned winner){
 unsigned best=0;for(unsigned k=1;k<HDC_CLASSES;k++)if(expected[c][k]>expected[c][best])best=k;
 return winner==best && !memcmp(scores,expected[c],sizeof(scores));
}
void app_main(void){
 printf("ESP32_HDC target=esp32c3 core=%d classes=%d D=%u configured_mhz=%d idf=%s\n",
  esp_cpu_get_core_id(),HDC_CLASSES,HDC_DIM,CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ,esp_get_idf_version());
 printf("NOTICE: QEMU guest counters are NOT cycle-accurate ESP32 latency measurements.\n");
 hdc_init(&ctx);
 for(unsigned c=0;c<4;c++){
  load(c);memset(query,0,sizeof(query));
  unsigned winner=hdc_packed32(&ctx,model,features,HDC_CLASSES,scores,query);
  if(!matches(c,winner) || memcmp(query,queries[c],sizeof(query))){printf("ESP32_HDC FAIL case=%u\n",c);return;}
  printf("ESP32_HDC VERIFY PASS case=%u winner=%u\n",c,winner);
 }
 load(2);
 for(unsigned sample=0;sample<9;sample++){
  portENTER_CRITICAL(&lock);
  uint32_t begin=esp_cpu_get_cycle_count();
  unsigned winner=hdc_packed32(&ctx,model,features,HDC_CLASSES,scores,0);
  uint32_t end=esp_cpu_get_cycle_count();
  portEXIT_CRITICAL(&lock);
  if(!matches(2,winner)){printf("ESP32_HDC FAIL timed query\n");return;}
  printf("ESP32_HDC SAMPLE sample=%u guest_counter_delta=%" PRIu32 " winner=%u score=%u\n",
    sample,end-begin,winner,scores[winner]);
 }
 printf("ESP32_HDC PASS classes=%d; functional simulation only; count instructions for analytical timing\n",HDC_CLASSES);
}
