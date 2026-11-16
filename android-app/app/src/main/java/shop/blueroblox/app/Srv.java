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
