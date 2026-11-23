package shop.blueroblox.app;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 16/11c — CÂU MÁY CHỦ (tiếng Việt) → tiếng Anh khi app đang dùng English. SINH TỰ ĐỘNG từ i18n/server.json (v2/gen/make_srv.py) — đừng sửa tay.
 *  Câu không có trong bảng mà còn chữ Việt → câu tiếng Anh chung (không bao giờ để lọt tiếng Việt khi khách chọn English). */
final class Srv {
    private Srv() { }
    static final String GENERIC = "Something went wrong on the server — try again in a moment or contact support.";
    private static final String[][] R = {
            {"Máy chủ chưa lấy được hình của máy này\\. Bấm [“\"]Khởi động lại máy[”\"] để sửa \\(1–2 phút, dữ liệu giữ nguyên\\) — vẫn lỗi thì báo hỗ trợ\\.", "The server couldn't get this phone's screen. Tap “Restart phone” to fix it (1–2 minutes, your data is kept) — if it still fails, contact support.", ""},
            {"Máy chưa bật lại được — máy chủ sẽ tự thử lại\\. Bấm [“\"]Khởi động lại máy[”\"] để sửa nhanh; quá 5 phút vẫn vậy thì báo hỗ trợ\\.", "The phone couldn't be started yet — the server will keep trying. Tap “Restart phone” for a quick fix; if it's still like this after 5 minutes, contact support.", ""},
            {"🔄 Máy đang được bật lại — khoảng 1–2 phút, đã (\\d+) giây\\. Tự vào khi máy lên\\.", "🔄 The phone is starting — about 1–2 minutes ({1} s so far). You'll get in automatically when it's up.", ""},
            {"🔄 Máy đang được bật lại — khoảng 1–2 phút\\. Tự vào khi máy lên\\.", "🔄 The phone is starting — about 1–2 minutes. You'll get in automatically when it's up.", ""},
            {"🔄 Máy đang khởi động lại — máy chủ đang bận nên lâu hơn bình thường, đã (\\d+) giây\\. Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào\\.", "🔄 The phone is restarting — the server is busy, so it's taking longer than usual ({1} s so far). You can leave; it keeps restarting — open it again to get in.", ""},
            {"🔄 Máy đang khởi động lại — khoảng 1–2 phút, đã (\\d+) giây\\. Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào\\.", "🔄 The phone is restarting — about 1–2 minutes ({1} s so far). You can leave; it keeps restarting — open it again to get in.", ""},
            {"🔄 Máy đang khởi động lại — khoảng 1–2 phút\\. Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào\\.", "🔄 The phone is restarting — about 1–2 minutes. You can leave; it keeps restarting — open it again to get in.", ""},
            {"Máy đang bật nhưng Android chưa trả lời, đã (\\d+) giây\\. Chờ thêm ít phút, hoặc bấm [“\"]Khởi động lại máy[”\"] để sửa nhanh \\(1–2 phút, dữ liệu giữ nguyên\\)\\.", "The phone is on but Android isn't responding yet ({1} s). Wait a few more minutes, or tap “Restart phone” for a quick fix (1–2 minutes, your data is kept).", ""},
            {"Máy đang bật nhưng Android chưa trả lời\\. Chờ thêm ít phút, hoặc bấm [“\"]Khởi động lại máy[”\"] để sửa nhanh \\(1–2 phút, dữ liệu giữ nguyên\\)\\.", "The phone is on but Android isn't responding yet. Wait a few more minutes, or tap “Restart phone” for a quick fix (1–2 minutes, your data is kept).", ""},
            {"Máy đang tạm dừng trên máy chủ\\. Bấm [“\"]Khởi động lại máy[”\"] để bật lại; không được thì báo hỗ trợ\\.", "The phone is paused on the server. Tap “Restart phone” to start it again; if that doesn't work, contact support.", ""},
            {"Máy chủ chưa có máy này \\(có thể đang được tạo lại\\)\\. Chờ ít phút; vẫn vậy thì báo hỗ trợ kèm tên máy\\.", "The server doesn't have this phone yet (it may be being recreated). Wait a few minutes; if it stays like this, contact support with the phone's name.", ""},
            {"💤 Máy đang thức dậy sau khi tự nghỉ \\(lâu không dùng\\) — khoảng 1 phút, đã (\\d+) giây\\.", "💤 The phone is waking up after resting (unused for a while) — about 1 minute ({1} s so far).", ""},
            {"💤 Máy đang thức dậy sau khi tự nghỉ \\(lâu không dùng\\) — khoảng 1 phút\\.", "💤 The phone is waking up after resting (unused for a while) — about 1 minute.", ""},
            {"Máy chưa thức dậy sau 4 phút — mở lại sau ít phút hoặc báo hỗ trợ\\.", "The phone hasn't woken up after 4 minutes — reopen it in a few minutes or contact support.", ""},
            {"Máy chưa lên sau 4 phút — bấm [“\"]Khởi động lại máy[”\"] hoặc báo hỗ trợ\\.", "The phone isn't up after 4 minutes — tap “Restart phone” or contact support.", ""},
            {"Máy không còn tồn tại\\.", "This phone no longer exists.", ""},
            {"Chủ máy đã tắt chia sẻ hoặc đã chuyển máy — bạn không còn quyền dùng máy này\\.", "The owner stopped sharing or transferred this phone — you no longer have access.", ""},
            {"Thiếu mã máy\\.", "Missing phone ID.", ""},
            {"Phiên đăng nhập hết hạn, hãy đăng nhập lại\\.", "Session expired, please log in again.", ""},
            {"Không tìm thấy máy\\.", "Phone not found.", ""},
            {"Đây không phải máy của bạn\\.", "This isn't your phone.", ""},
            {"Máy nằm ở máy chủ khác — hãy mở lại\\.", "This phone is on another server — please reopen it.", ""},
            {"Máy chưa chạy \\(đang tạo, tạm dừng hoặc đã hết hạn\\)\\.", "The phone isn't running (being created, paused or expired).", ""},
            {"Máy chưa sẵn sàng, thử lại sau ít giây\\.", "The phone isn't ready yet, try again in a few seconds.", ""},
            {"Máy chưa sẵn sàng\\.", "The phone isn't ready yet.", ""},
            {"Máy đang bị khoá: liên hệ hỗ trợ\\.", "This phone is locked — contact support.", ""},
            {"Máy đang bị khoá: (.+)", "This phone is locked: {1}", ""},
            {"Hệ thống đang bảo trì, quay lại sau ít phút\\.", "Under maintenance — please come back in a few minutes.", ""},
            {"Không lấy được hình từ cửa sổ máy — thử mở lại\\.", "Couldn't get the phone's picture — try reopening it.", ""},
            {"Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại\\.", "The phone is off or restarting — wait a few seconds, then reopen it.", ""},
            {"Máy đang tắt hoặc đang khởi động lại\\.", "The phone is off or restarting.", ""},
            {"Máy đang được mở ở nơi khác\\.", "This phone was opened somewhere else.", ""},
            {"Đang mở máy ở kết nối khác\\.", "The phone is being opened on another connection.", ""},
            {"Màn hình Android của máy này đang lỗi \\(máy chủ không lấy được hình\\)\\. Bấm [“\"]Khởi động lại máy[”\"] để sửa — vẫn lỗi thì báo hỗ trợ\\.", "This phone's Android screen has a problem (the server can't get the picture). Tap “Restart phone” to fix it — if it still fails, contact support.", ""},
            {"Máy chủ đang bận — tạm tắt hình xem trước\\.", "The server is busy — live preview is paused.", ""},
            {"Máy đang được xem trước ở nhiều nơi\\.", "This phone is being previewed in too many places.", ""},
            {"Chưa bật được hình xem trước\\.", "Couldn't start the live preview.", ""},
            {"Máy đang nghỉ — mở máy để bật lại\\.", "The phone is resting — open it to wake it up.", ""},
            {"Máy chủ chưa bật được hình — thử lại\\.", "The server couldn't start the picture — retrying.", ""},
            {"Máy chủ đang bận, thử lại…", "The server is busy, retrying…", ""},
            {"Hệ thống đang bảo trì: (.+)\\. Vui lòng quay lại sau\\.", "Under maintenance: {1}. Please come back later.", ""},
            {"Hệ thống đang bảo trì\\. Vui lòng quay lại sau\\.", "Under maintenance. Please come back later.", ""},
            {"Máy đang bị khoá đến (\\S+ \\S+): (.+)\\. Liên hệ hỗ trợ nếu cần\\.", "This phone is locked until {1}: {2}. Contact support if needed.", ""},
            {"Máy đang bị khoá đến (\\S+ \\S+)\\. Liên hệ hỗ trợ nếu cần\\.", "This phone is locked until {1}. Contact support if needed.", ""},
            {"Máy đang bị khoá vĩnh viễn: (.+)\\. Liên hệ hỗ trợ nếu cần\\.", "This phone is locked: {1}. Contact support if needed.", ""},
            {"Máy đang bị khoá vĩnh viễn\\. Liên hệ hỗ trợ nếu cần\\.", "This phone is locked. Contact support if needed.", ""},
            {"Không có chức năng này\\.", "This feature isn't available.", ""},
            {"Không được phép\\.", "Not allowed.", ""},
            {"Nguồn không được phép\\.", "Source not allowed.", ""},
            {"Phiên đăng nhập hết hạn — tải lại trang và đăng nhập lại\\.", "Session expired — reload and log in again.", ""},
            {"Không tìm thấy máy của bạn\\.", "Your phone wasn't found.", ""},
            {"Máy chưa chạy \\(đang tạo, tạm dừng hoặc đã huỷ\\)\\.", "The phone isn't running (being created, paused or cancelled).", ""},
            {"Hãy mở máy từ app hoặc trang web\\.", "Open the phone from the app or the website.", ""},
            {"Máy phản hồi quá lâu, thử lại\\.", "The phone took too long to respond, try again.", ""},
            {"Không có việc này\\.", "Job not found.", ""},
            {"Chỉ admin\\.", "Admins only.", ""},
            {"Không có file này\\.", "File not found.", ""},
            {"Phím không hợp lệ\\.", "Invalid key.", ""},
            {"Chưa nhập chữ\\.", "No text entered.", ""},
            {"Chỉ dán được chữ KHÔNG DẤU\\. Chữ có dấu hãy gõ trực tiếp trên màn hình máy\\.", "Only plain text without accents can be pasted. Type accented text directly on the phone screen.", ""},
            {"Link phải bắt đầu bằng http:// hoặc https://", "The link must start with http:// or https://", ""},
            {"Chưa xoay được — máy chưa sẵn sàng, thử lại sau giây lát\\.", "Couldn't rotate — the phone isn't ready, try again shortly.", ""},
            {"Chưa đọc được màn hình máy — thử lại sau giây lát\\.", "Couldn't read the phone's screen — try again shortly.", ""},
            {"Chưa lấy được mã — mở Cửa hàng Play 1 lần, đợi 1 phút rồi thử lại\\.", "Couldn't get the ID yet — open the Play Store once, wait 1 minute, then try again.", ""},
            {"Không có app này trong kho\\.", "This app isn't in the store.", ""},
            {"Tên app không hợp lệ\\.", "Invalid app name.", ""},
            {"Tên ứng dụng không hợp lệ\\.", "Invalid app name.", ""},
            {"Đã tắt vị trí giả\\.", "Fake location turned off.", ""},
            {"Toạ độ không hợp lệ\\.", "Invalid coordinates.", ""},
            {"Đổi vị trí GPS cần máy Android 12 trở lên\\.", "Changing the GPS location needs Android 12 or newer.", ""},
            {"Đã bỏ các bản clone\\.", "Clones removed.", ""},
            {"Chưa có bản clone này — bấm Clone trước\\.", "This clone doesn't exist yet — tap Clone first.", ""},
            {"Số bản clone không hợp lệ\\.", "Invalid number of clones.", ""},
            {"Máy này chỉ đủ chạy (\\d+) bản clone cho mượt \\(mỗi bản cần \\+3GB RAM, \\+2 nhân\\)\\. Chọn ít bản hơn, hoặc bấm Nâng cấp RAM/CPU\\.", "This phone can only run {1} clone(s) smoothly (each needs +3GB RAM, +2 cores). Choose fewer, or tap Upgrade RAM/CPU.", ""},
            {"Máy ([\\d.]+)GB / ([\\d.]+) nhân chưa đủ để chạy thêm .+", "A {1}GB / {2}-core phone isn't enough for clones (it would freeze). Clone tab needs at least 6GB RAM + 4 cores for 1 clone (+3GB RAM, +2 cores for each extra) — upgrade the phone first.", ""},
            {"Máy chưa cài app này — cài bản chính trước rồi mới clone\\.", "This app isn't installed — install the main app first, then clone it.", ""},
            {"Android trong máy không cho tạo hồ sơ clone\\.", "Android on this phone doesn't allow clone profiles.", ""},
            {"Đã mở bản clone (\\d+) của (.+)\\.", "Opened clone {1} of {2}.", ""},
            {"Mã tải lên không hợp lệ\\.", "Invalid upload ID.", ""},
            {"File rỗng hoặc lớn hơn 4GB\\.", "The file is empty or larger than 4GB.", ""},
            {"Server tạm hết dung lượng, thử lại sau\\.", "The server is out of space, try again later.", ""},
            {"Lệch vị trí", "Upload position mismatch", "j"},
            {"Dữ liệu vượt kích thước file\\.", "The data is larger than the file.", ""},
            {"FPS phải từ (\\d+) đến (\\d+)\\.", "FPS must be between {1} and {2}.", ""},
            {"FPS phải từ (\\d+) đến (\\d+)", "FPS must be between {1} and {2}", ""},
            {"FPS không hợp lệ\\.", "Invalid FPS.", ""},
            {"Máy dưới 4 nhân chỉ chọn tối đa 60 FPS \\(treo game nên để 30 FPS cho mượt\\)\\.", "Phones under 4 cores can use up to 60 FPS (30 FPS is best for idling games).", ""},
            {"Máy dưới 4 nhân chỉ chọn tối đa 60 FPS\\.?", "Phones under 4 cores can use up to 60 FPS.", ""},
            {"Độ phân giải phải dạng rộng x cao, VD 1080x1920\\.", "Resolution must be width x height, e.g. 1080x1920.", ""},
            {"Máy đang được đổi cấu hình, đợi chút\\.", "The phone's setup is being changed, please wait.", ""},
            {"Không xác định được máy\\.", "Couldn't identify the phone.", ""},
            {"Thiếu bật / tắt root\\.", "Missing root on / off.", ""},
            {"Danh sách app không hợp lệ\\.", "Invalid app list.", ""},
            {"Đang lưu cấu hình root của máy này, đợi vài giây\\.", "Saving this phone's root settings, wait a few seconds.", ""},
            {"Chế độ không hợp lệ\\.", "Invalid mode.", ""},
            {"Máy đang bị khoá — mở khoá trước rồi hãy ép khởi động lại\\.", "The phone is locked — unlock it before forcing a restart.", ""},
            {"Máy đang khởi động lại / đổi cấu hình — đợi xong rồi thử lại\\.", "The phone is restarting / changing setup — wait until it's done, then try again.", ""},
            {"Đang bảo trì\\.", "Under maintenance.", ""},
            {"Lỗi máy chủ: .*", "Server error — try again.", ""},
            {"Chỉ nhận file \\.apk / \\.apks / \\.apkm / \\.xapk", "Only .apk / .apks / .apkm / .xapk files are accepted", ""},
            {"Link không phải file APK\\.", "The link isn't an APK file.", ""},
            {"Link không hợp lệ \\(chỉ nhận link http/https công khai\\)\\.", "Invalid link (public http/https links only).", ""},
            {"File quá lớn \\(tối đa 4GB\\)\\.", "File too large (max 4GB).", ""},
            {"File đã hết hạn, tải lên lại\\.", "The file expired — upload it again.", ""},
            {"File gói hỏng hoặc bị mã hoá\\.", "The package file is corrupted or encrypted.", ""},
            {"Gói không có file \\.apk bên trong\\.", "The package has no .apk inside.", ""},
            {"Link này là TRANG WEB, không phải link tải file\\..*", "This link is a WEB PAGE, not a file download. Open it on your computer, tap Download, then copy the real download link (usually ending in .apk) and paste it here — or download the file and use “Upload file / APK”.", ""},
            {"Không tải được từ Google Drive — hãy chia sẻ file ở chế độ [“\"]Bất kỳ ai có đường liên kết[”\"]\\.", "Couldn't download from Google Drive — share the file as “Anyone with the link”.", ""},
            {"Độ rộng nhỏ nhất phải từ 240 đến 1600 dp\\.", "Smallest width must be between 240 and 1600 dp.", ""},
            {"Độ rộng nhỏ nhất không hợp lệ\\.", "Invalid smallest width.", ""},
            {"Máy chủ chưa cập nhật bản có Root theo app — báo admin cập nhật\\.", "The server doesn't support per-app root yet — ask an admin to update it.", ""},
            {"Không lưu được cấu hình root, thử lại sau\\.", "Couldn't save root settings, try again later.", ""},
            {"Cấu hình root đọc được bị lỗi\\.", "The root settings are corrupted.", ""},
            {"Không chụp được màn hình\\.", "Couldn't take a screenshot.", ""},
            {"Máy hết bộ nhớ — xoá bớt file / gỡ bớt app rồi thử lại\\.", "The phone is out of storage — delete some files or apps and try again.", ""},
            {"Máy chủ của máy này chưa có tính năng này — đang được cập nhật, thử lại sau\\.", "This phone's server doesn't have this feature yet — try again later.", ""},
            {"Đang khởi động Android \\(1–3 phút\\)…", "Starting Android (1–3 minutes)…", ""},
            {"Đang tắt hẳn máy \\(máy treo thì tắt cưỡng bức\\)…", "Shutting the phone down fully (force-stopping it if frozen)…", ""},
            {"Máy đã khởi động lại xong\\.", "The phone has restarted.", ""},
            {"Máy đã khởi động, đang kết nối lại…", "The phone has started, reconnecting…", ""},
            {"Máy đã bật lại, đang kết nối….*", "The phone is back on, connecting…", ""},
            {"Đã ép khởi động lại xong.*", "Forced restart done.", ""},
            {"Đang kiểm tra / bật root \\(máy có thể khởi động lại ~1 phút\\)…", "Checking / enabling root (the phone may restart, ~1 minute)…", ""},
            {"✅ Máy đã ROOT\\. Tool cần root \\(gọi lệnh su\\) dùng được ngay, không cần khởi động lại\\.", "✅ The phone is ROOTED. Tools that need root (su) work right away, no restart needed.", ""},
            {"⏳ Máy đang bật root, chờ 1 phút rồi bấm lại\\.", "⏳ Root is being enabled — wait 1 minute, then tap again.", ""},
            {"Đang bật root cho app đã chọn… \\(máy chưa có root gốc sẽ tự khởi động lại ~1 phút\\)", "Enabling root for the selected apps… (a phone without base root restarts, ~1 minute)", ""},
            {"Đang tắt root…", "Turning root off…", ""},
            {"Đã lưu\\.", "Saved.", "j"},
            {"Máy đang khởi động lại với chế độ mới \\(khoảng 1–2 phút\\)…", "Restarting the phone with the new mode (about 1–2 minutes)…", ""},
            {"Đã chuyển sang MƯỢT\\.", "Switched to SMOOTH.", ""},
            {"Đã chuyển sang HIỆN 3D\\.", "Switched to 3D DISPLAY.", ""},
            {"Đã đổi, đang kết nối lại…", "Changed, reconnecting…", ""},
            {"Đang áp dụng và khởi động lại máy \\(1–3 phút\\)…", "Applying and restarting the phone (1–3 minutes)…", ""},
            {"Đang đổi kích thước màn hình…", "Changing the screen size…", ""},
            {"Đã đổi sang (\\S+) · (\\d+) FPS\\. Dữ liệu vẫn giữ nguyên\\.", "Changed to {1} · {2} FPS. Your data is kept.", ""},
            {"Đã đổi sang (\\S+) — app đang chạy vẫn giữ nguyên\\.", "Changed to {1} — running apps keep running.", ""},
            {"Đang tạo (\\d+) bản clone \\(mỗi bản ~20 giây\\)…", "Creating {1} clone(s) (~20 s each)…", ""},
            {"✅ Đã có (\\d+) bản clone! Mở lại Clone tab.*", "✅ {1} clone(s) ready! Reopen Clone tab and tap ▶ Open clone 1, 2… to run them (or use the Work tab in the app list).", ""},
            {"✅ Đã có (\\d+) bản clone! Trên màn hình chính máy.*", "✅ {1} clone(s) ready! The phone's home screen has whale icons “Clone 1”, “Clone 2”… — tap one to open it.", ""},
            {"Đã có (\\d+) bản clone\\. Máy cần KHỞI ĐỘNG LẠI 1 lần.*", "{1} clone(s) exist. The phone needs ONE restart to add more — tap “Restart”, then clone again.", ""},
            {"Đã có (\\d+) bản clone — máy này chỉ cho tối đa.*", "{1} clone(s) exist — that's the most this phone allows. For more accounts, rent another phone.", ""},
            // 23/11 · 🗗 tab cửa sổ nhỏ (cpapi /win)
            {"Đã thu nhỏ (.+) \\(bản clone\\) \\((\\d+) tab nhỏ\\)\\..*", "Minimized {1} (clone) ({2} small tabs). Drag the top bar to move it, drag an edge to resize.", ""},
            {"Đã thu nhỏ (.+) \\((\\d+) tab nhỏ\\)\\..*", "Minimized {1} ({2} small tabs). Drag the top bar to move it, drag an edge to resize.", ""},
            {"Đã xếp (\\d+) tab nhỏ \\((\\d+) cột × (\\d+) hàng\\)\\. Màn nhỏ nên.*", "Arranged {1} small tabs ({2} × {3}). The screen is small, so they overlap — raise 📐 Smallest width (e.g. 600 dp) so they don't.", ""},
            {"Đã xếp (\\d+) tab nhỏ \\((\\d+) cột × (\\d+) hàng\\)\\.", "Arranged {1} small tabs ({2} × {3}).", ""},
            {"Đã phóng to (.+) \\(bản clone\\) ra toàn màn\\.", "{1} (clone) is full screen again.", ""},
            {"Đã phóng to (.+) ra toàn màn\\.", "{1} is full screen again.", ""},
            {"Đã phóng to (.+) hết màn\\. .*", "{1} now fills the screen. For true full screen, tap ▭ on the window's title bar.", ""},
            {"Đã mở lại (.+) ngay trong cửa sổ — game vẽ vừa khung \\(game vừa khởi động lại, vào lại trận nếu cần\\)\\.", "Reopened {1} inside its window — the game now fits (it just restarted; rejoin your match if needed).", ""},
            {"Chưa có tab nhỏ nào đang hiện — thu nhỏ app \\(VD Roblox\\) trước rồi bấm Mở lại vừa khung\\.", "No small tab is showing — minimize an app (e.g. Roblox) first, then tap Refit to window.", ""},
            // 23/11d–e · game vừa khung thật (mở lại ngay trong tab) · xoay màn thật
            {"Đã thu nhỏ (.+) \\(bản clone\\) \\((\\d+) tab nhỏ\\) — game đã mở lại để vẽ vừa cửa sổ\\. Máy chuyển sang màn rộng (\\d+) dp.*", "Minimized {1} (clone) ({2} small tabs) — the game reopened so it fits its window. The phone switched to a wide {3} dp screen so tabs have room — tap Normal portrait to undo.", ""},
            {"Đã thu nhỏ (.+) \\((\\d+) tab nhỏ\\) — game đã mở lại để vẽ vừa cửa sổ\\. Máy chuyển sang màn rộng (\\d+) dp.*", "Minimized {1} ({2} small tabs) — the game reopened so it fits its window. The phone switched to a wide {3} dp screen so tabs have room — tap Normal portrait to undo.", ""},
            {"Đã thu nhỏ (.+) \\(bản clone\\) \\((\\d+) tab nhỏ\\) — game đã mở lại để vẽ vừa cửa sổ\\.", "Minimized {1} (clone) ({2} small tabs) — the game reopened so it fits its window.", ""},
            {"Đã thu nhỏ (.+) \\((\\d+) tab nhỏ\\) — game đã mở lại để vẽ vừa cửa sổ\\.", "Minimized {1} ({2} small tabs) — the game reopened so it fits its window.", ""},
            {"Đã xếp (\\d+) tab nhỏ \\((\\d+) cột × (\\d+) hàng\\)\\. (\\d+) game đã mở lại để vẽ vừa ô mới\\. Màn nhỏ nên.*", "Arranged {1} small tabs ({2} × {3}). {4} game(s) reopened to fit the new size. The screen is small, so they overlap — raise 📐 Smallest width (e.g. 600 dp) so they don't.", ""},
            {"Đã xếp (\\d+) tab nhỏ \\((\\d+) cột × (\\d+) hàng\\)\\. (\\d+) game đã mở lại để vẽ vừa ô mới\\.", "Arranged {1} small tabs ({2} × {3}). {4} game(s) reopened to fit the new size.", ""},
            {"Đã phóng to (.+) \\(bản clone\\) ra toàn màn\\. Game đã mở lại để vẽ đủ toàn màn\\. Máy đã về mật độ cũ \\((\\d+) dp\\)\\.", "{1} (clone) is full screen again — the game reopened to fill the screen. The phone is back to its previous screen density ({2} dp).", ""},
            {"Đã phóng to (.+) ra toàn màn\\. Game đã mở lại để vẽ đủ toàn màn\\. Máy đã về mật độ cũ \\((\\d+) dp\\)\\.", "{1} is full screen again — the game reopened to fill the screen. The phone is back to its previous screen density ({2} dp).", ""},
            {"Đã phóng to (.+) \\(bản clone\\) ra toàn màn\\. Game đã mở lại để vẽ đủ toàn màn\\.", "{1} (clone) is full screen again — the game reopened to fill the screen.", ""},
            {"Đã phóng to (.+) ra toàn màn\\. Game đã mở lại để vẽ đủ toàn màn\\.", "{1} is full screen again — the game reopened to fill the screen.", ""},
            {"Đã phóng to (.+) ra toàn màn\\. Hình chưa đủ màn thì bấm Vừa khung\\.", "{1} is full screen again. If the picture doesn't fill the screen, tap Refit to window.", ""},
            {"Đã mở lại (.+) ngay trong cửa sổ — game vẽ vừa khung \\(game vừa khởi động lại, vào lại trận nếu cần\\)\\. Hình vẫn bị cắt.*", "Reopened {1} inside its window — the game now fits (it just restarted; rejoin your match if needed). Still cut off? Tap Wide landscape so the window has room.", ""},
            {"Đã mở lại (.+) toàn màn — game vẽ đủ màn \\(game vừa khởi động lại, vào lại trận nếu cần\\)\\.", "Reopened {1} full screen — the game now fills the screen (it just restarted; rejoin your match if needed).", ""},
            {"Chưa mở lại được (.+) — tắt app rồi mở lại từ màn chính\\.", "Couldn't reopen {1} — close the app and open it again from the home screen.", ""},
            {"Đã xoay màn NGANG\\.", "The screen is now landscape.", ""},
            {"Máy này chưa xoay ngang được màn chính — .*", "This phone's home screen can't turn landscape yet — apps / games that need landscape still show landscape.", ""},
            {"Đã về màn DỌC — .*", "Back to portrait — the open app / game needs landscape, so it still shows landscape.", ""},
            {"Đã về màn DỌC\\.", "The screen is back to portrait.", ""},
            {"Đã khoá màn NGANG\\.", "Locked to landscape.", ""},
            {"Đã khoá màn DỌC\\.", "Locked to portrait.", ""},
            {"Chưa phóng to được tab — .*", "Couldn't maximize the tab — tap the ⬜ button on that window's title bar.", ""},
            {"Thiếu việc cần làm \\(thu nhỏ / sắp xếp / phóng to / mở lại vừa khung / to hơn / nhỏ hơn / màn ngang rộng\\)\\.", "Missing action.", ""},
            // 23/11c · cửa sổ to hơn / nhỏ hơn · màn ngang rộng
            {"Cửa sổ (.+) \\(bản clone\\) đã to hơn \\((\\d+)×(\\d+)\\)\\. Bấm tiếp để to nữa\\.", "The {1} (clone) window is bigger ({2}×{3}). Tap again to grow it more.", ""},
            {"Cửa sổ (.+) \\(bản clone\\) đã nhỏ hơn \\((\\d+)×(\\d+)\\)\\. Bấm tiếp để nhỏ nữa\\.", "The {1} (clone) window is smaller ({2}×{3}). Tap again to shrink it more.", ""},
            {"Cửa sổ (.+) đã to hơn \\((\\d+)×(\\d+)\\)\\. Bấm tiếp để to nữa\\.", "The {1} window is bigger ({2}×{3}). Tap again to grow it more.", ""},
            {"Cửa sổ (.+) đã nhỏ hơn \\((\\d+)×(\\d+)\\)\\. Bấm tiếp để nhỏ nữa\\.", "The {1} window is smaller ({2}×{3}). Tap again to shrink it more.", ""},
            {"Cửa sổ đã to nhất rồi \\(hết màn\\) — muốn to nữa bấm Phóng to tab\\.", "The window already fills the screen — tap Maximize tab to go bigger.", ""},
            {"Cửa sổ đã nhỏ nhất rồi \\(Android không cho nhỏ hơn\\) — .*", "The window is already as small as Android allows — tap 🖥 Wide landscape to fit more tabs.", ""},
            {"Chưa có tab nhỏ nào đang hiện — thu nhỏ app \\(VD Roblox\\) trước rồi bấm Cửa sổ to hơn / nhỏ hơn\\.", "No small tab is showing — minimize an app (e.g. Roblox) first, then tap Bigger / Smaller window.", ""},
            {"Đã bật màn NGANG RỘNG \\((\\d+) dp\\) — màn chính nằm ngang, chứa được nhiều tab hơn\\..*", "Wide landscape is on ({1} dp) — the home screen is landscape and fits more tabs.", ""},
            {"Đã đặt màn rộng \\((\\d+) dp\\) \\+ khoá ngang — .*", "Wide screen set ({1} dp) + landscape lock — this phone's home screen doesn't rotate; landscape apps / games still show landscape.", ""},
            {"Đã trả màn DỌC như cũ \\((\\d+) dp\\)\\..*", "Back to the normal portrait screen ({1} dp).", ""},
            {"Chưa mở lại được (.+) trong cửa sổ — thử lại, hoặc mở app rồi bấm Thu nhỏ tab\\.", "Couldn't reopen {1} in its window — try again, or open the app and tap Minimize tab.", ""},
            {"Chưa có app nào đang mở toàn màn — .*", "No app is open full screen — open an app (e.g. Roblox), then tap Minimize tab.", ""},
            {"Các tab đang là cửa sổ nhỏ rồi — .*", "Your tabs are already small windows — open another tab (e.g. a clone), then tap Minimize tab.", ""},
            {"Máy chưa bật được cửa sổ nhỏ — .*", "Small windows aren't on yet on this phone — tap ⚡ Restart once, then try again.", ""},
            {"Chưa có tab nhỏ nào — .*", "No small tabs yet — open an app and tap Minimize tab first.", ""},
            {"Chưa có tab nhỏ nào đang hiện trên màn hình\\.", "No small tab is on the screen.", ""},
            {"Chưa phóng to được tab — .*", "Couldn't maximize the tab — tap the ⬜ button on that window's title bar.", ""},
            {"Android của máy này quá cũ, chưa có cửa sổ nhỏ\\.", "This phone's Android is too old for small windows.", ""},
            {"Android của máy này chưa đọc được danh sách tab — .*", "Couldn't read this phone's tabs — try again in a moment.", ""},
            {"Đang xếp tab của máy này, đợi vài giây\\.", "Arranging this phone's tabs — wait a few seconds.", ""},
            {"Thiếu việc cần làm \\(thu nhỏ / sắp xếp / phóng to\\)\\.", "Missing action (minimize / arrange / maximize).", ""},
            {"Đã đặt vị trí (.+)\\. Mở lại app cần vị trí để nhận vị trí mới\\.", "Location set to {1}. Reopen apps that use location to get the new one.", ""},
            {"✅ Đã cài (.+) — mở trên màn hình chính của máy\\.", "✅ Installed {1} — open it from the phone's home screen.", ""},
            {"Đã cài xong (.+?)( \\(kèm (\\d+) file dữ liệu game\\))?", "Installed {1}", "j"},
            {"✅ Đã cài (.+)", "✅ Installed {1}", "j"},
            {"Đang cài (.+)", "Installing {1}", "j"},
            {"Đã lưu vào thư mục Download: (.+)", "Saved to the Download folder: {1}", ""},
            {"Đã tải (.+)", "Downloaded {1}", "j"},
            {"Không lấy được (.+) từ trang chính chủ \\(.*\\)\\. Thử lại sau ít phút\\.", "Couldn't download {1} from the official site. Try again in a few minutes.", ""},
            {"Không khởi động lại được: .*", "Couldn't restart the phone — try again in a minute or contact support.", ""},
            {"Không ép khởi động lại được: .*", "Couldn't force-restart the phone — try again in a minute or contact support.", ""},
            {"Chưa khởi động lại được: .*", "Couldn't restart yet — try again in a minute.", ""},
            {"Không đổi được: .*", "Couldn't change it — try again later.", ""},
            {"Đổi cấu hình lỗi: .*", "Couldn't change the setup — try again later.", ""},
            {"Chưa root được: .*", "Couldn't root the phone — try again later.", ""},
            {"Không đọc được cấu hình root: .*", "Couldn't read the root settings.", ""},
            {"Chưa clone được: .*", "Couldn't clone — try again later.", ""},
            {"Chưa mở được bản clone: .*", "Couldn't open the clone.", ""},
            {"Chưa đặt được vị trí: .*", "Couldn't set the location.", ""},
            {"Cài APK lỗi: .*", "Couldn't install the APK.", ""},
            {"Không chép được file vào máy: .*", "Couldn't copy the file to the phone.", ""},
            {"Không chép được file: .*", "Couldn't copy the file.", ""},
            {"Chỉ chủ máy mới xem / đặt được proxy của máy này\\.", "Only the phone's owner can view or set its proxy.", ""},
            {"Máy chủ chưa cập nhật bản có Proxy — báo admin cập nhật\\.", "The server doesn't support proxies yet — ask an admin to update it.", ""},
            {"Không đọc được proxy của máy, thử lại sau\\.", "Couldn't read this phone's proxy, try again later.", ""},
            {"Đọc proxy bị lỗi, thử lại sau\\.", "Reading the proxy failed, try again later.", ""},
            {"Thiếu việc cần làm \\(lưu / tắt / áp dụng lại\\)\\.", "Missing action (save / turn off / apply again).", ""},
            {"Proxy không hợp lệ\\.", "Invalid proxy.", ""},
            {"Kiểu proxy không hợp lệ\\.", "Invalid proxy type.", ""},
            {"Đang áp dụng proxy cho máy này, đợi vài giây\\.", "Applying this phone's proxy, wait a few seconds.", ""},
            {"Đang bật proxy \\(kiểm tra proxy \\+ gắn vào máy, ~10–30 giây\\)…", "Turning the proxy on (checking it and attaching it to the phone, ~10–30 s)…", ""},
            {"Đang tắt proxy…", "Turning the proxy off…", ""},
            {"Đang áp dụng lại proxy…", "Applying the proxy again…", ""},
            {"Không áp dụng được proxy, thử lại sau\\.", "Couldn't apply the proxy, try again later.", ""},
            {"Kiểu proxy phải là Tự nhận / SOCKS5 / HTTP\\.", "The proxy type must be Auto / SOCKS5 / HTTP.", ""},
            {"Chưa nhập proxy\\.", "No proxy entered.", ""},
            {"Proxy có ký tự lạ\\.", "The proxy contains invalid characters.", ""},
            {"Chưa hỗ trợ proxy HTTPS \\(mã hoá tới proxy\\) — dùng HTTP hoặc SOCKS5\\.", "HTTPS proxies (encrypted to the proxy) aren't supported — use HTTP or SOCKS5.", ""},
            {"Thiếu cổng — nhập dạng IP:cổng hoặc IP:cổng:user:pass\\.", "Missing port — use IP:port or IP:port:user:pass.", ""},
            {"Cổng proxy phải là số \\(1–65535\\)\\.", "The proxy port must be a number (1–65535).", ""},
            {"Cổng proxy phải từ 1 đến 65535\\.", "The proxy port must be between 1 and 65535.", ""},
            {"Chưa hỗ trợ proxy IPv6 — dùng địa chỉ IPv4 hoặc tên miền\\.", "IPv6 proxies aren't supported — use an IPv4 address or a domain name.", ""},
            {"Địa chỉ proxy không hợp lệ \\(IP hoặc tên miền\\)\\.", "Invalid proxy address (IP or domain name).", ""},
            {"Địa chỉ proxy không hợp lệ\\.", "Invalid proxy address.", ""},
            {"User / mật khẩu proxy quá dài hoặc có ký tự lạ\\.", "The proxy user / password is too long or has invalid characters.", ""},
            {"Máy chưa đặt proxy\\.", "This phone has no proxy set.", ""},
            {"Đã tắt proxy\\.", "Proxy turned off.", ""},
            {"Đã lưu — máy đang tắt, proxy tự bật khi máy bật\\.", "Saved — the phone is off; the proxy turns on when it starts.", ""},
            {"Máy không dùng proxy — đang đi mạng thường\\.", "This phone isn't using a proxy — it's on the normal network.", ""},
            {"Đã TẮT proxy — máy đi mạng thường\\.", "Proxy turned OFF — the phone uses the normal network.", ""},
            {"Máy không cho máy chủ quyền root để tắt proxy — khởi động lại máy là proxy tự tắt\\.", "The phone didn't give the server root to turn the proxy off — restarting the phone turns it off.", ""},
            {"Không tìm được IP của proxy (.+) — kiểm tra lại địa chỉ\\.", "Couldn't find the IP of proxy {1} — check the address.", ""},
            {"Máy chưa có quyền root cho máy chủ \\(cần để bật proxy\\) — bấm 🔓 Root máy rồi thử lại\\.", "The phone hasn't given the server root (needed for the proxy) — tap 🔓 Root phone, then try again.", ""},
            {"Máy không cho máy chủ quyền root — chưa bật được proxy\\.", "The phone didn't give the server root — the proxy isn't on yet.", ""},
            {"Đã BẬT proxy — IP ra: (\\S+) · (\\d+) ms", "Proxy ON — exit IP: {1} · {2} ms", ""},
            {"Đã lưu proxy nhưng proxy CHƯA dùng được \\((.+)\\) — máy đang đi mạng thường, tự thử lại mỗi 15 giây\\.", "Proxy saved, but it does NOT work yet ({1}) — the phone uses the normal network and retries every 15 s.", ""},
            {"Chưa bật được proxy: (.+)", "Couldn't turn the proxy on: {1}", ""},
            {"Chưa áp dụng được: (.+)", "Couldn't apply it yet: {1}", ""},
            {"Khởi động lại", "Restart", "j"},
            {"Ép khởi động lại", "Forced restart", "j"},
            {"Root máy", "Root phone", "j"},
            {"Đổi chế độ hình", "Change display mode", "j"},
            {"Cài (.+)", "Install {1}", "j"},
    };
    private static Pattern[] pat;
    private static final Pattern VN = Pattern.compile("[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

    private static synchronized Pattern[] pats() {
        if (pat == null) {
            Pattern[] p = new Pattern[R.length];
            for (int i = 0; i < R.length; i++) {
                try { p[i] = Pattern.compile(R[i][0], Pattern.DOTALL); } catch (Exception e) { p[i] = null; }
            }
            pat = p;
        }
        return pat;
    }

    /** Còn chữ tiếng Việt (có dấu)? */
    static boolean hasVi(String s) { return s != null && VN.matcher(s).find(); }

    /** Câu tiếng Anh của s theo bảng; null = không có. job = true: dùng cả mẫu chung của VIỆC (tên việc / tiến độ). */
    static String find(String s, boolean job) {
        if (s == null) return null;
        String t = s.trim();
        if (t.isEmpty()) return null;
        Pattern[] p = pats();
        for (int i = 0; i < p.length; i++) {
            if (p[i] == null || (!job && "j".equals(R[i][2]))) continue;
            Matcher m = p[i].matcher(t);
            if (!m.matches()) continue;
            String out = R[i][1];
            for (int g = 9; g >= 1; g--) out = out.replace("{" + g + "}", g <= m.groupCount() && m.group(g) != null ? m.group(g) : "");
            return out;
        }
        return null;
    }

    /** Câu hiện cho khách khi dùng English: có trong bảng → câu dịch; không có mà còn chữ Việt → fallback (null = câu chung). */
    static String en(String s, boolean job, String fallback) {
        if (s == null || s.trim().isEmpty() || !hasVi(s)) return s;
        String f = find(s, job);
        if (f != null) return f;
        int nl = s.indexOf('\n');                                  // nhiều dòng: dịch từng dòng
        if (nl > 0) {
            StringBuilder b = new StringBuilder();
            for (String ln : s.split("\n")) {
                String x = ln.trim().isEmpty() ? ln : en(ln, job, null);
                if (x == null) return fallback != null ? fallback : GENERIC;
                if (b.length() > 0) b.append('\n');
                b.append(x);
            }
            return b.toString();
        }
        return fallback != null ? fallback : (job ? null : GENERIC);
    }
}
