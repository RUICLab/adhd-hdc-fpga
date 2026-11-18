#ifndef HDC_PACKED_H
#define HDC_PACKED_H
#include <stdint.h>
#define HDC_DIM 8192u
#define HDC_FEATURES 196u
#define HDC_WORDS 7u
#define HDC_QUERY_WORDS (HDC_DIM/32u)
typedef struct { uint32_t flip[13][HDC_WORDS]; } hdc_context;
void hdc_init(hdc_context *ctx);
/* Model[j]: low four bits = level bits; next K bits = class prototypes.
 * Optional query output is indexed in NATURAL dimension order. It must be
 * zeroed by the caller. Pass NULL to omit query storage during timing.
 * All class scores and lowest-index winning class are returned. */
unsigned hdc_packed32(const hdc_context *ctx,const uint32_t *model,
                      const uint8_t *features,unsigned classes,
                      uint16_t *scores,uint32_t *query);
#endif
