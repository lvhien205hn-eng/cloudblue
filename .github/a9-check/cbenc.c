/*
 * CloudBlue cbenc (27/11h) — bộ nén H.264 RIÊNG cho cbvideo (máy Android 9 / LDPlayer 9), thay OMX.google.h264.encoder.
 * openh264 (Cisco, BSD-2-Clause, https://github.com/cisco/openh264) liên kết tĩnh + JNI cho com.cloudblue.A9Video.
 *
 * Vì sao: bộ nén OMX của Android 9 chạy trong tiến trình media 32-bit có seccomp, luồng phụ libavc chờ bằng sched_yield → ~50–60 ms / khung
 * (đo CI simpleperf) → chỉ ~15 khung/giây. Ở đây: RGBA (ImageReader) → I420 (C, -O3) → openh264 SCREEN_CONTENT_REAL_TIME, 1 lát / khung,
 * baseline (CAVLC), không bỏ khung, IDR khi được xin — tất cả trong tiến trình cbvideo 64-bit, không qua binder.
 */
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "codec_api.h"

typedef struct {
    ISVCEncoder *enc;
    int w, h, fps, last_type;
    uint8_t *yuv;          /* I420 khung gần nhất (nén lại khi màn đứng yên / xin IDR lúc không có khung mới) */
    double last_ms;        /* thời gian nén khung gần nhất (ms) */
} Ctx;

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}

/* RGBA (R,G,B,A theo byte) → I420, BT.601 giới hạn 16–235 (như scrcpy / bộ nén Android), chroma = trung bình khối 2×2. */
static void rgba_to_i420(const uint8_t *s, int rs, uint8_t *y, uint8_t *u, uint8_t *v, int w, int h) {
    int cw = w >> 1;
    for (int j = 0; j < h; j += 2) {
        const uint8_t *a = s + (size_t)j * rs, *b = a + rs;
        uint8_t *y0 = y + (size_t)j * w, *y1 = y0 + w, *uu = u + (size_t)(j >> 1) * cw, *vv = v + (size_t)(j >> 1) * cw;
        for (int i = 0; i < cw; i++) {
            int r0 = a[0], g0 = a[1], b0 = a[2], r1 = a[4], g1 = a[5], b1 = a[6];
            int r2 = b[0], g2 = b[1], b2 = b[2], r3 = b[4], g3 = b[5], b3 = b[6];
            y0[0] = (uint8_t)(((66 * r0 + 129 * g0 + 25 * b0 + 128) >> 8) + 16);
            y0[1] = (uint8_t)(((66 * r1 + 129 * g1 + 25 * b1 + 128) >> 8) + 16);
            y1[0] = (uint8_t)(((66 * r2 + 129 * g2 + 25 * b2 + 128) >> 8) + 16);
            y1[1] = (uint8_t)(((66 * r3 + 129 * g3 + 25 * b3 + 128) >> 8) + 16);
            int R = r0 + r1 + r2 + r3, G = g0 + g1 + g2 + g3, B = b0 + b1 + b2 + b3;
            uu[i] = (uint8_t)(((-38 * R - 74 * G + 112 * B + 512) >> 10) + 128);
            vv[i] = (uint8_t)(((112 * R - 94 * G - 18 * B + 512) >> 10) + 128);
            a += 8; b += 8; y0 += 2; y1 += 2;
        }
    }
}

JNIEXPORT jlong JNICALL Java_com_cloudblue_A9Video_nInit(JNIEnv *env, jclass cls, jint w, jint h, jint fps, jint bps, jint intra, jint threads) {
    (void) env; (void) cls;
    Ctx *c = (Ctx *) calloc(1, sizeof(Ctx));
    if (!c) return 0;
    c->w = w; c->h = h; c->fps = fps > 0 ? fps : 30;
    c->yuv = (uint8_t *) calloc((size_t) w * h * 3 / 2, 1);
    if (!c->yuv || WelsCreateSVCEncoder(&c->enc) != 0 || !c->enc) { free(c->yuv); free(c); return 0; }
    SEncParamExt p;
    memset(&p, 0, sizeof(p));
    (*c->enc)->GetDefaultParams(c->enc, &p);
    p.iUsageType = SCREEN_CONTENT_REAL_TIME;
    p.iPicWidth = w; p.iPicHeight = h;
    p.iTargetBitrate = bps; p.iMaxBitrate = UNSPECIFIED_BIT_RATE;
    p.iRCMode = RC_BITRATE_MODE;
    p.fMaxFrameRate = (float) c->fps;
    p.uiIntraPeriod = intra > 0 ? (unsigned int) intra : 0;
    p.iMultipleThreadIdc = threads > 0 ? threads : 1;
    p.bEnableFrameSkip = false;
    p.iEntropyCodingModeFlag = 0;
    p.iComplexityMode = LOW_COMPLEXITY;
    p.bEnableDenoise = false;
    p.bEnableBackgroundDetection = true;
    p.bEnableAdaptiveQuant = false;
    p.bEnableSceneChangeDetect = false;
    p.bEnableLongTermReference = false;
    p.bPrefixNalAddingCtrl = false;
    p.eSpsPpsIdStrategy = CONSTANT_ID;
    p.iSpatialLayerNum = 1; p.iTemporalLayerNum = 1;
    p.uiMaxNalSize = 0;
    p.iLoopFilterDisableIdc = 0;
    p.sSpatialLayers[0].iVideoWidth = w;
    p.sSpatialLayers[0].iVideoHeight = h;
    p.sSpatialLayers[0].fFrameRate = (float) c->fps;
    p.sSpatialLayers[0].iSpatialBitrate = bps;
    p.sSpatialLayers[0].iMaxSpatialBitrate = UNSPECIFIED_BIT_RATE;
    p.sSpatialLayers[0].uiProfileIdc = PRO_BASELINE;
    p.sSpatialLayers[0].sSliceArgument.uiSliceMode = SM_SINGLE_SLICE;
    if ((*c->enc)->InitializeExt(c->enc, &p) != cmResultSuccess) {
        WelsDestroySVCEncoder(c->enc); free(c->yuv); free(c); return 0;
    }
    int fmt = videoFormatI420;
    (*c->enc)->SetOption(c->enc, ENCODER_OPTION_DATAFORMAT, &fmt);
    return (jlong) (intptr_t) c;
}

/* Nén c->yuv → out (Annex-B, mã đầu 4 byte). Trả số byte (0 = bỏ qua, < 0 = lỗi / out nhỏ). */
static int encode_yuv(Ctx *c, int64_t pts_us, int idr, uint8_t *out, int cap) {
    SSourcePicture pic;
    memset(&pic, 0, sizeof(pic));
    pic.iPicWidth = c->w; pic.iPicHeight = c->h; pic.iColorFormat = videoFormatI420;
    pic.iStride[0] = c->w; pic.iStride[1] = pic.iStride[2] = c->w >> 1;
    pic.pData[0] = c->yuv;
    pic.pData[1] = c->yuv + (size_t) c->w * c->h;
    pic.pData[2] = pic.pData[1] + (size_t) (c->w >> 1) * (c->h >> 1);
    pic.uiTimeStamp = (long long) (pts_us / 1000);
    if (idr) (*c->enc)->ForceIntraFrame(c->enc, true);
    SFrameBSInfo info;
    memset(&info, 0, sizeof(info));
    double t0 = now_ms();
    int r = (*c->enc)->EncodeFrame(c->enc, &pic, &info);
    c->last_ms = now_ms() - t0;
    if (r != cmResultSuccess) return -1;
    c->last_type = info.eFrameType;
    if (info.eFrameType == videoFrameTypeSkip) return 0;
    int total = 0;
    for (int l = 0; l < info.iLayerNum; l++) {
        SLayerBSInfo *L = &info.sLayerInfo[l];
        int sz = 0;
        for (int n = 0; n < L->iNalCount; n++) sz += L->pNalLengthInByte[n];
        if (total + sz > cap) return -2;
        memcpy(out + total, L->pBsBuf, (size_t) sz);
        total += sz;
    }
    return total;
}

JNIEXPORT jint JNICALL Java_com_cloudblue_A9Video_nEncode(JNIEnv *env, jclass cls, jlong hd, jobject rgba, jint rs, jlong pts, jboolean idr, jobject out) {
    (void) cls;
    Ctx *c = (Ctx *) (intptr_t) hd;
    if (!c) return -3;
    uint8_t *src = (uint8_t *) (*env)->GetDirectBufferAddress(env, rgba);
    uint8_t *dst = (uint8_t *) (*env)->GetDirectBufferAddress(env, out);
    jlong cap = (*env)->GetDirectBufferCapacity(env, out);
    if (!src || !dst || cap <= 0) return -4;
    uint8_t *y = c->yuv, *u = y + (size_t) c->w * c->h, *v = u + (size_t) (c->w >> 1) * (c->h >> 1);
    rgba_to_i420(src, rs, y, u, v, c->w, c->h);
    return encode_yuv(c, pts, idr ? 1 : 0, dst, (int) cap);
}

/* Nén lại khung I420 gần nhất (màn đứng yên cho nét dần · xin IDR lúc không có khung mới). */
JNIEXPORT jint JNICALL Java_com_cloudblue_A9Video_nEncodeLast(JNIEnv *env, jclass cls, jlong hd, jlong pts, jboolean idr, jobject out) {
    (void) cls;
    Ctx *c = (Ctx *) (intptr_t) hd;
    if (!c) return -3;
    uint8_t *dst = (uint8_t *) (*env)->GetDirectBufferAddress(env, out);
    jlong cap = (*env)->GetDirectBufferCapacity(env, out);
    if (!dst || cap <= 0) return -4;
    return encode_yuv(c, pts, idr ? 1 : 0, dst, (int) cap);
}

/* Loại khung vừa nén: 1 IDR · 2 I · 3 P · 4 bỏ qua (openh264 EVideoFrameType). */
JNIEXPORT jint JNICALL Java_com_cloudblue_A9Video_nType(JNIEnv *env, jclass cls, jlong hd) {
    (void) env; (void) cls;
    Ctx *c = (Ctx *) (intptr_t) hd;
    return c ? c->last_type : 0;
}

/* Thời gian nén khung gần nhất, phần trăm mili-giây (vd 312 = 3,12 ms). */
JNIEXPORT jint JNICALL Java_com_cloudblue_A9Video_nLastMs100(JNIEnv *env, jclass cls, jlong hd) {
    (void) env; (void) cls;
    Ctx *c = (Ctx *) (intptr_t) hd;
    return c ? (jint) (c->last_ms * 100.0) : 0;
}

JNIEXPORT void JNICALL Java_com_cloudblue_A9Video_nBitrate(JNIEnv *env, jclass cls, jlong hd, jint bps) {
    (void) env; (void) cls;
    Ctx *c = (Ctx *) (intptr_t) hd;
    if (!c) return;
    SBitrateInfo bi;
    memset(&bi, 0, sizeof(bi));
    bi.iLayer = SPATIAL_LAYER_ALL;
    bi.iBitrate = bps;
    (*c->enc)->SetOption(c->enc, ENCODER_OPTION_BITRATE, &bi);
}

JNIEXPORT void JNICALL Java_com_cloudblue_A9Video_nClose(JNIEnv *env, jclass cls, jlong hd) {
    (void) env; (void) cls;
    Ctx *c = (Ctx *) (intptr_t) hd;
    if (!c) return;
    if (c->enc) { (*c->enc)->Uninitialize(c->enc); WelsDestroySVCEncoder(c->enc); }
    free(c->yuv);
    free(c);
}
