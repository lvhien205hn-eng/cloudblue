package shop.blueroblox.app;

import android.content.Context;
import android.graphics.Color;
import android.view.View;
import android.widget.FrameLayout;

import org.json.JSONObject;

/**
 * Ô xem trước TRỰC TIẾP 1 máy (thẻ máy ở "Máy của tôi" và lưới "Xem tất cả"): hình nhỏ (cạnh dài ≤ 480, 4G: ≤ 320), ~8 khung/giây,
 * chỉ xem — bấm vào ô (ô cha nhận bấm) là mở màn điều khiển. Không đá phiên điều khiển đang mở ở nơi khác.
 * Chưa có hình / tạm dừng / máy chủ chưa hỗ trợ → ô tĩnh (biểu tượng + trạng thái) phủ lên trên.
 * Cùng 1 ô được chuyển qua lại giữa danh sách và "Xem tất cả" (không phải nối lại). MainActivity bật / tạm dừng theo ô có đang hiện trên màn hình không.
 */
final class LivePreview extends FrameLayout implements StreamClient.Listener, StreamView.Events {
    final String id;
    private final StreamView screen;
    private final FrameLayout cover;
    private final int maxh;
    private StreamClient client;
    private boolean ended = false, released = false, frame = false;
    /** Lúc ô bắt đầu khuất khỏi màn hình (0 = đang hiện) — MainActivity tạm dừng ô khuất lâu. */
    long hiddenAt = 0;

    LivePreview(Context c, String phoneId, int videoW, int videoH, int maxh) {
        super(c);
        id = phoneId;
        this.maxh = maxh;
        setBackgroundColor(Color.BLACK);
        screen = new StreamView(c, true);
        screen.setEvents(this);
        screen.setVideoSize(videoW, videoH);                          // đúng tỉ lệ ngay từ đầu (độ phân giải máy đã mua)
        addView(screen, new LayoutParams(-1, -1));
        cover = new FrameLayout(c);
        cover.setBackgroundColor(Color.rgb(2, 4, 12));
        addView(cover, new LayoutParams(-1, -1));
    }

    /** Nội dung ô tĩnh (vẽ theo trạng thái máy mỗi lần danh sách / lưới vẽ lại). */
    void setCover(View v) {
        cover.removeAllViews();
        if (v != null) cover.addView(v, new LayoutParams(-1, -1));
    }

    boolean playing() { return client != null; }

    /** Đã dừng hẳn (máy chủ chưa hỗ trợ / bị từ chối) — không tự bật lại cho tới khi retry(). */
    boolean ended() { return ended; }

    /** Bật hình (đang bật / đã dừng hẳn → bỏ qua). */
    void play() {
        if (client != null || ended || released) return;
        client = new StreamClient(getContext(), id, "eco", this).preview(maxh);
        screen.attach(client);
        client.start();
    }

    /** Tắt hình, giữ ô (bật lại bằng play()). */
    void pause() {
        if (client != null) { client.close(); client = null; }
        screen.attach(null);
        showCover(true);
    }

    /** Cho ô đã dừng hẳn thử lại (bấm "Làm mới"). */
    void retry() { ended = false; }

    /** Sắp chuyển / gỡ nhiều ô cùng lúc: dừng bộ giải mã trước (song song) để lúc gỡ không làm đứng giao diện. */
    void park() { if (!released) screen.dropSurface(); }

    /** Bỏ hẳn ô: đóng kết nối + bộ giải mã + luồng giải mã. */
    void release() {
        if (released) return;
        pause();
        released = true;
        screen.release();
    }

    private void showCover(boolean show) {
        if (show) {
            frame = false;
            cover.animate().cancel();
            cover.setAlpha(1f);
            cover.setVisibility(VISIBLE);
        } else if (cover.getVisibility() == VISIBLE) {
            cover.animate().alpha(0f).setDuration(180).withEndAction(() -> { if (frame) cover.setVisibility(GONE); }).start();
        }
    }

    @Override protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        showCover(true);                 // Surface bị huỷ khi gỡ ô → gắn lại thì ô tĩnh che tới khi có khung khoá mới (≤ 1 giây)
    }

    // ---- StreamView.Events ----
    @Override public void onFirstFrame() {
        if (client == null || released) return;
        frame = true;
        showCover(false);
    }

    @Override public void onTouchDown() { }

    // ---- StreamClient.Listener (luồng giao diện) ----
    @Override public void onConnecting(int attempt, String why) { }
    @Override public void onEndpoint(JSONObject ep) { }
    @Override public void onWelcome(JSONObject welcome, boolean direct) { }
    @Override public void onClipboard(String text) { }
    @Override public void onStats(int fps, int kbps, int pingMs, boolean direct, JSONObject server) { }
    @Override public void onProblem(String code, String msg) { }

    @Override public void onStopped(String code, String msg) {
        ended = true;                    // NO_PREVIEW / PREVIEW_LIMIT / NOT_ACTIVE / LOGIN… → giữ ô tĩnh
        pause();
    }
}
