# -*- coding: utf-8 -*-
# =====================================================================================================
#  CloudBlue PC — BẢN TIẾNG ANH (16/11c). App vẫn viết tiếng Việt; khi khách chọn English, mọi chữ hiện ra
#  (Tk: nhãn, nút, menu, hộp thoại, tiêu đề cửa sổ · cửa sổ máy pygame) đi qua tr() → câu tiếng Anh.
#  Không khớp câu nào → giữ nguyên (không bao giờ làm hỏng chữ). SINH TỰ ĐỘNG (pc/i18n/build_en.py) — đừng sửa tay.
# =====================================================================================================
import re

EXACT = {
"Bản app này đã cũ — phải cập nhật mới dùng tiếp được.": "This app version is too old — please update to keep using it.",
"Sai email hoặc mật khẩu.": "Wrong email or password.",
"Email chưa xác nhận — mở hộp thư để xác nhận.": "Email not confirmed — open your inbox to confirm it.",
"Phiên đăng nhập hết hạn, hãy đăng nhập lại.": "Your session has expired — please log in again.",
"Hãy đăng nhập.": "Please log in.",
"Bạn không có quyền mở máy này.": "You don't have permission to open this phone.",
"Không tìm thấy máy.": "Phone not found.",
"Hệ thống đang bảo trì.": "The system is under maintenance.",
"Máy còn dưới 30 phút — gia hạn trước rồi hãy đổi Android.": "Less than 30 minutes left on this phone — renew it first, then switch Android.",
"Máy đang nâng cấp / gia hạn — chờ 1–2 phút rồi đổi Android.": "The phone is being upgraded / renewed — wait 1–2 minutes, then switch Android.",
"Máy đang đổi Android — chờ máy mới tạo xong (2–5 phút).": "The phone is switching Android — wait until the new phone is ready (2–5 minutes).",
"Máy đang chạy bản Android này rồi.": "The phone is already on this Android version.",
"Mỗi tài khoản đổi Android tối đa 3 lần trong 24 giờ.": "Each account can switch Android at most 3 times in 24 hours.",
"Không tìm thấy máy (hoặc máy không phải của bạn).": "Phone not found (or it isn't yours).",
"Máy phải đang chạy mới làm được việc này.": "The phone must be running to do this.",
"Máy đang bị khoá.": "This phone is locked.",
"Bản Android này chưa bán.": "This Android version isn't on sale yet.",
"Máy chủ bản Android này đang bảo trì — thử lại sau.": "The server for this Android version is under maintenance — try again later.",
"Máy chủ bản Android này đang hết chỗ — chọn bản khác hoặc thử lại sau.": "The server for this Android version is full — pick another version or try again later.",
"Không có kết nối mạng.": "No network connection.",
"sai chứng chỉ máy chủ": "bad server certificate",
"Mất kết nối tới máy chủ, thử lại.": "Lost connection to the server — try again.",
"Không nối được tới máy chủ của máy này — kiểm tra mạng rồi thử lại.": "Couldn't reach this phone's server — check your network and try again.",
"Có lỗi.": "Something went wrong.",
"Việc chạy quá lâu — kiểm tra lại máy sau ít phút.": "The task is taking too long — check the phone again in a few minutes.",
"File rỗng.": "The file is empty.",
"Máy chủ chưa nhận đủ file — thử lại.": "The server didn't receive the whole file — try again.",
"Tự động": "Auto",
"Siêu nét": "Sharp",
"Cân bằng": "Balanced",
"Tiết kiệm": "Saver",
"Quay lại": "Back",
"Màn chính": "Home",
"Đa nhiệm": "Recents",
"Âm +": "Vol +",
"Âm −": "Vol −",
"Chụp màn": "Screenshot",
"Dán chữ": "Paste text",
"Công cụ": "Tools",
"Chất lượng": "Quality",
"Toàn màn": "Full screen",
"Ẩn thanh": "Hide bar",
"Thu nhỏ tab": "Minimize tab",
"Sắp xếp tab": "Arrange tabs",
"Phóng to tab": "Maximize tab",
"Tab cửa sổ nhỏ": "Small tab windows",
"Tab cửa sổ nhỏ · Xoay màn · Độ rộng nhỏ nhất…": "Small tab windows · Rotate screen · Smallest width…",
"Mở app (VD Roblox) rồi bấm Thu nhỏ tab: app thành cửa sổ nhỏ ngay trên màn hình máy, vẫn chạy và bấm được. Mở tab khác (VD bản clone) rồi thu nhỏ tiếp. Kéo thanh trên cùng của cửa sổ để dời, kéo mép để đổi cỡ.": "Open an app (e.g. Roblox), then tap Minimize tab: it becomes a small window right on the phone's screen, still running and clickable. Open another tab (e.g. a clone) and minimize it too. Drag a window's top bar to move it, drag an edge to resize.",
"Đang thu nhỏ tab…": "Minimizing the tab…",
"Đang sắp xếp tab…": "Arranging tabs…",
"Đang phóng to tab…": "Maximizing the tab…",
"Thông số": "Stats",
"Đang kết nối…": "Connecting…",
"Máy chưa chạy (đang tạo, tạm dừng hoặc đã hết hạn).": "The phone isn't running (being created, paused or expired).",
"📶 Mạng yếu — đã giảm nét cho hình mượt.": "📶 Weak network — quality lowered to stay smooth.",
"⏳ Mạng chậm — đang chờ hình…": "⏳ Slow network — waiting for video…",
"Bấm lần nữa (hoặc phím K) để KHỞI ĐỘNG LẠI máy — khoảng 1–2 phút. App đang mở trong máy sẽ tắt, dữ liệu vẫn giữ nguyên.": "Press again (or the K key) to RESTART the phone — about 1–2 minutes. Apps open on the phone will close; your data is kept.",
"Đang khởi động lại máy… (1–2 phút)": "Restarting the phone… (1–2 minutes)",
"Chưa khởi động lại được: ": "Couldn't restart yet: ",
" Bấm R để thử lại; vẫn lỗi thì báo hỗ trợ kèm tên máy.": " Press R to try again; if it still fails, contact support with the phone's name.",
"lỗi": "error",
"Máy đã khởi động lại — đang kết nối…": "The phone has restarted — connecting…",
"Chưa có bản mới trên trang tải — báo shop giúp nhé.": "No new version on the download page yet — please tell the shop.",
"mới": "new",
"Không mở được trình cập nhật — mở app CloudBlue PC rồi bấm Cập nhật.": "Couldn't open the updater — open the CloudBlue PC app and click Update.",
"Đang cập nhật — app tự tải bản mới, đóng cửa sổ này rồi mở lại máy (khoảng 1 phút).": "Updating — the app downloads the new version; close this window and reopen the phone (about 1 minute).",
"Đang mở trình cập nhật…": "Opening the updater…",
"Đang lấy hình…": "Getting the picture…",
"Máy đang được mở ở nơi khác.": "This phone is open somewhere else.",
"Bấm phím R hoặc bấm vào đây để mở lại tại đây.": "Press R or click here to reopen it here.",
"Đang tìm bản mới…": "Looking for a new version…",
"App tự thử lại sau vài giây — không cần bấm gì.": "The app retries in a few seconds — nothing to click.",
"Bấm phím K (hoặc bấm vào đây) để KHỞI ĐỘNG LẠI MÁY · phím R: thử lại.": "Press K (or click here) to RESTART THE PHONE · R: retry.",
"Bấm phím R để thử lại.": "Press R to try again.",
"Máy đang được bật lên (thức dậy / khởi động) — thường 1–2 phút, app tự vào khi máy lên.": "The phone is starting up (waking / booting) — usually 1–2 minutes; the app gets in automatically when it's up.",
" · mạng yếu (đã giảm nét)": " · weak network (quality lowered)",
"Đang xoay ngang…": "Rotating to landscape…",
"Đang xoay dọc…": "Rotating to portrait…",
"Đã khoá màn NGANG. App đang mở chỉ chạy màn dọc nên chưa xoay — mở game / app hỗ trợ ngang là tự ngang.": "Locked to LANDSCAPE. The open app only runs in portrait, so it hasn't rotated — open a game / app that supports landscape and it rotates by itself.",
"Đã khoá màn DỌC. App đang mở chỉ chạy màn ngang nên chưa xoay.": "Locked to PORTRAIT. The open app only runs in landscape, so it hasn't rotated.",
"Đang chụp màn hình…": "Taking a screenshot…",
"Không chụp được màn hình": "Couldn't take a screenshot",
"Đã ẩn thanh công cụ — bấm dải mỏng bên phải hoặc phím F10 để hiện lại.": "Toolbar hidden — click the thin strip on the right or press F10 to show it again.",
"Toàn màn hình — bấm phím F11 (hoặc nút Toàn màn) để thoát.": "Full screen — press F11 (or the Full screen button) to exit.",
"Đang tải lại hình…": "Reloading the picture…",
"Không mở được cửa sổ máy. Chi tiết trong:\n": "Couldn't open the phone window. Details in:\n",
"Đang chạy": "Running",
"Đang tạo…": "Creating…",
"Hết hạn — chờ gia hạn": "Expired — waiting for renewal",
"Lỗi": "Error",
"đã hết hạn": "expired",
"Nhẹ máy": "Light",
"HD+ dài": "Tall HD+",
"Ổn định · phổ biến": "Stable · popular",
"Mới": "New",
"Mới nhất": "Newest",
"Nhẹ": "Light",
"Số dư không đủ.": "Not enough balance.",
"Máy đang bị khoá, không gia hạn được. Liên hệ hỗ trợ.": "This phone is locked and can't be renewed. Contact support.",
"⛔ Tài khoản đã bị cấm do vi phạm điều khoản sử dụng. Nếu là nhầm lẫn, liên hệ hỗ trợ kèm tên đăng nhập.": "⛔ This account has been banned for breaking the terms of use. If this is a mistake, contact support with your username.",
"Số tiền thấp hơn mức nạp tối thiểu.": "The amount is below the minimum top-up.",
"Bạn có quá nhiều lệnh nạp đang chờ. Thử lại sau ít phút.": "You have too many pending top-ups. Try again in a few minutes.",
"RAM nằm ngoài giới hạn cho phép.": "RAM is outside the allowed range.",
"Số nhân CPU nằm ngoài giới hạn cho phép.": "CPU cores are outside the allowed range.",
"Số ngày nằm ngoài giới hạn cho phép.": "Days are outside the allowed range.",
"Độ phân giải không hợp lệ.": "Invalid resolution.",
"FPS nằm ngoài giới hạn cho phép.": "FPS is outside the allowed range.",
"Số lượng không hợp lệ.": "Invalid quantity.",
"Máy dưới 4 nhân chỉ chọn tối đa 60 FPS.": "Phones with fewer than 4 cores can only pick up to 60 FPS.",
"Đã hết hàng.": "Sold out.",
"Tài khoản đã đủ số máy cho phép — gia hạn máy đang có hoặc xoá máy cũ để thuê máy khác.": "Your account has reached its phone limit — renew a phone you have or delete an old one to rent another.",
"Ưu đãi miễn phí đã kết thúc.": "The free offer has ended.",
"Máy miễn phí vượt cấu hình tối đa cho phép.": "The free phone exceeds the maximum allowed setup.",
"Mỗi tài khoản chỉ được dùng thử 1 máy miễn phí — bạn đã nhận rồi.": "Each account gets only 1 free trial phone — you've already had yours.",
"Máy miễn phí chỉ nhận 1 máy mỗi lần.": "Free phones are 1 at a time.",
"Máy miễn phí không gia hạn được — hãy thuê máy mới.": "Free phones can't be renewed — rent a new phone.",
"Máy chủ đã hết chỗ cho cấu hình này. Chọn cấu hình nhỏ hơn hoặc quay lại sau.": "The server is full for this setup. Pick a smaller setup or come back later.",
"Máy chủ bản Android này đang bảo trì — chọn bản khác.": "The server for this Android version is under maintenance — pick another version.",
"Bản Android này chưa bán — chọn bản khác.": "This Android version isn't on sale yet — pick another version.",
"Máy đã bị xoá vì hết hạn quá 30 phút — hãy thuê máy mới.": "The phone was deleted after being expired for over 30 minutes — rent a new phone.",
"đ": "đ",
"Treo app · nuôi acc": "Idle apps · farm accounts",
"Chạy 24/7 kể cả khi tắt máy tính": "Runs 24/7 even when your PC is off",
"Game nhẹ · treo cả ngày": "Light games · idle all day",
"Game 2D, nhàn rỗi, cờ, bài": "2D, idle, board and card games",
"Treo game nhẹ ổn định": "Stable light-game idling",
"Treo game 1 tab mượt": "Smooth 1-tab game idling",
"🔥 Bán chạy": "🔥 Best seller",
"1 tab game, đồ hoạ thấp": "1 game tab, low graphics",
"Game dùng ~2GB RAM — vẫn còn dư": "Games use ~2GB RAM — still room to spare",
"⭐ Đề xuất": "⭐ Recommended",
"2–4 tab game cùng lúc": "2–4 game tabs at once",
"Mỗi tab thêm cần ~1,5–2GB RAM": "Each extra tab needs ~1.5–2GB RAM",
"Game nặng 3D · 60 FPS": "Heavy 3D games · 60 FPS",
"Free Fire, Liên Quân, PUBG Mobile…": "Free Fire, Arena of Valor, PUBG Mobile…",
"Không có card đồ hoạ — game nặng có thể giật": "No graphics card — heavy games may stutter",
"Bảo trì": "Maintenance",
"Hết chỗ": "Full",
"— vượt trần": "— over the limit",
"/ ngày": "/ day",
"Chọn": "Choose",
"✓ Đã chọn": "✓ Selected",
"Đang tải…": "Loading…",
"Có lỗi, thử lại.": "Something went wrong — try again.",
"Áp dụng": "Apply",
"Mã giảm giá (nếu có) — nhập rồi bấm Áp dụng.": "Discount code (if any) — enter it, then click Apply.",
"🎫 Mã của bạn:": "🎫 Your codes:",
"⏳ Đang kiểm tra mã…": "⏳ Checking the code…",
"ℹ Giá CTV của bạn đã rẻ hơn — mã sẽ không được dùng (không mất lượt).": "ℹ Your reseller price is already lower — the code won't be used (you don't lose it).",
" Sửa hoặc xoá mã giảm giá để thanh toán.": " Edit or remove the discount code to pay.",
"Chưa kiểm tra được mã, thử lại.": "Couldn't check the code — try again.",
"📱 Mở máy đám mây": "📱 Open a cloud phone",
"🔗 Chia sẻ link mời": "🔗 Share your invite link",
"👥 Bạn được mời nạp tiền": "👥 A friend you invited tops up",
"🎁 Bạn được mời nạp tiền lần đầu": "🎁 A friend you invited tops up for the first time",
"\n\nDùng Blue: bật \"💎 Trả bằng Blue\" khi thuê / gia hạn máy — 1 Blue = 1đ": "\n\nUsing Blue: turn on \"💎 Pay with Blue\" when renting / renewing a phone — 1 Blue = 1đ",
", trả được cả đơn.": ", can pay a whole order.",
" để mở khoá trả bằng Blue (vẫn tích bình thường).": " to unlock paying with Blue (you still earn it as usual).",
"\n🔒 Nạp tiền": "\n🔒 Top up",
" ít nhất 1 lần": " at least once",
"\n\nXem lại bất cứ lúc nào: bấm nút 💎 trên app.": "\n\nCheck it any time: click the 💎 button in the app.",
"  💎 Trả bằng Blue": "  💎 Pay with Blue",
"🔒 Nạp tiền lần đầu để dùng Blue (Blue vẫn được tích).": "🔒 Top up for the first time to use Blue (you still earn Blue).",
"Chưa có Blue — điểm danh, làm nhiệm vụ để tích (bấm 💎 Tích Blue trên danh sách máy).": "No Blue yet — check in and do missions to earn it (click 💎 Earn Blue on the phone list).",
"Điểm danh hôm nay": "Check in today",
"Ngày nào cũng ghé là có Blue": "Drop by every day to get Blue",
"Mở máy đám mây": "Open a cloud phone",
"Mở 1 máy bất kỳ (app PC, app Android hoặc web) là tự nhận": "Open any phone (PC app, Android app or web) to get it automatically",
"Chia sẻ link mời": "Share your invite link",
"Copy link CloudBlue của bạn gửi bạn bè / nhóm": "Copy your CloudBlue link and send it to friends / groups",
"Bạn được mời nạp tiền": "A friend you invited tops up",
"Có bạn đăng ký qua link của bạn và NẠP TIỀN trong hôm nay": "Someone signed up through your link and TOPPED UP today",
"Điểm danh": "Check-in",
"Thưởng chuỗi": "Streak bonus",
"Nhiệm vụ": "Mission",
"Mời bạn": "Invite",
"Hoàn đơn": "Order cashback",
"Đã dùng": "Used",
"Hoàn lại": "Refund",
"Thu lại": "Taken back",
"Kiếm tiền (video)": "Earn money (videos)",
"💎 Tích Blue": "💎 Earn Blue",
"Tích Blue đang tạm tắt.": "Earn Blue is paused for now.",
"Chưa mở được Tích Blue — máy chủ chưa bật tính năng này.": "Couldn't open Earn Blue — the server hasn't turned this feature on yet.",
"1 Blue = 1đ khi thuê / gia hạn điện thoại đám mây": "1 Blue = 1đ when renting / renewing cloud phones",
" — bật 💎 Trả bằng Blue lúc thanh toán.": " — turn on 💎 Pay with Blue at checkout.",
"🧊 Blue của bạn đang được tạm giữ để kiểm tra (không nhận / không dùng được). Liên hệ hỗ trợ nếu cần.": "🧊 Your Blue is on hold for a check (can't be earned or used). Contact support if needed.",
" để mở khoá trả bằng Blue. Blue vẫn được tích bình thường.": " to unlock paying with Blue. You still earn Blue as usual.",
"🔒 Nạp tiền": "🔒 Top up",
" lần đầu": " for the first time",
"Chuỗi điểm danh": "Check-in streak",
"bắt đầu hôm nay": "starts today",
"Hôm nay": "Today",
"Nhiệm vụ hôm nay": "Today's missions",
"Bạn bạn mời đã nạp tiền hôm nay 🎉": "A friend you invited topped up today 🎉",
"Cần có 1 máy đang chạy — thuê máy rồi mở là nhận": "You need a running phone — rent one and open it to get this",
"✓ Đã nhận": "✓ Received",
"Chia sẻ": "Share",
"Copy link mời": "Copy invite link",
"Mở máy": "Open phone",
"Thuê máy": "Rent a phone",
"• Bạn bè bạn mời nạp tiền lần đầu": "• A friend you invited tops up for the first time",
"• Nhiệm vụ làm mới lúc 0 giờ mỗi ngày (giờ Việt Nam)": "• Missions reset at 0:00 every day (Vietnam time)",
"Nhận thêm Blue": "Earn more Blue",
"Lịch sử Blue": "Blue history",
"Đóng": "Close",
"Thuê điện thoại Android đám mây chạy 24/7 ở CloudBlue — đăng ký qua link của mình nhé: ": "Rent a 24/7 Android cloud phone at CloudBlue — sign up with my link: ",
"📋 Đã copy link mời — dán gửi bạn bè / nhóm (Zalo, Facebook, Discord…).": "📋 Invite link copied — paste it to friends / groups (Zalo, Facebook, Discord…).",
"🎡 Vòng quay": "🎡 Wheel",
"💰 Ưu đãi nạp": "💰 Top-up deals",
"🎁 Quà tặng": "🎁 Gifts",
"nền tảng khác": "other platforms",
"📱 Mở dùng thử 1 cloud phone miễn phí": "📱 Unlocks a free cloud phone trial",
" giờ ": " hours ",
"📱 Nhận máy dùng thử": "📱 Get a trial phone",
"Ưu đãi": "Deals",
"🎫 Mã của tôi": "🎫 My codes",
"Chỉ dùng cho cloud phone: nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn / nâng cấp máy — hoặc bấm chọn mã ngay dưới ô đó.": "Cloud phones only: enter it in the 🏷️ Discount code box when renting / renewing / upgrading — or pick a code right below that box.",
"Chưa có mã nào. Mã từ ưu đãi nạp, vòng quay, quà tặng sẽ nằm ở đây.": "No codes yet. Codes from top-up deals, the wheel and gifts show up here.",
"Dùng được đến ": "Valid until ",
"Đã tắt": "Disabled",
"Hết hạn": "Expired",
"Chép": "Copy",
" · 🤝 tặng bạn bè được": " · 🤝 can be gifted to friends",
"🎁 Mã giảm giá": "🎁 Discount code",
"Hiện chưa có ưu đãi nào.": "No deals right now.",
"💰 Ưu đãi khi nạp": "💰 Top-up deals",
". Chỉ dùng cho cloud phone: thuê, gia hạn, nâng cấp máy.": ". Cloud phones only: rent, renew, upgrade.",
" giờ": " hours",
" ngày": " days",
"✓ Bạn đã dùng thử rồi.": "✓ You've already used your trial.",
"Nhận máy dùng thử": "Get a trial phone",
"🎡 Vòng quay may mắn": "🎡 Lucky wheel",
"Mở vòng quay": "Open the wheel",
"🎬 Kiếm tiền": "🎬 Earn money",
"Xem cách làm": "How it works",
"Kiếm tiền": "Earn money",
"Chương trình Kiếm tiền đang tạm tắt.": "Earn money is paused for now.",
"1 💎 Blue = 1đ khi thuê / gia hạn cloud phone": "1 💎 Blue = 1đ when renting / renewing cloud phones",
" và nền tảng khác": " and other platforms",
"Cách làm": "How it works",
"1. Quay video giới thiệu CloudBlue — ví dụ treo game 24/7 trên cloud phone, cách thuê máy, so sánh giá.": "1. Record a video about CloudBlue — e.g. idling a game 24/7 on a cloud phone, how to rent a phone, price comparisons.",
"3. Dán link video vào ô bên dưới. Admin mở video kiểm tra rồi cộng 💎 theo số view.": "3. Paste the video link in the box below. An admin checks the video and adds 💎 based on the views.",
"4. View tăng thì bấm “Báo view mới” — mỗi lần duyệt cộng thêm 💎 cho phần view mới.": "4. When views grow, click “Report new views” — each approval adds 💎 for the new views.",
"• Video của chính bạn, để công khai. Không mua view, không đăng lại video người khác — vi phạm bị từ chối.": "• Your own videos, set to public. No bought views, no reposting other people's videos — violations are rejected.",
"• 💎 Blue chỉ dùng cho cloud phone (thuê / gia hạn), 1 💎 = 1đ": "• 💎 Blue is for cloud phones only (rent / renew), 1 💎 = 1đ",
". Không dùng cho sản phẩm khác.": ". Not for other products.",
"Gửi video": "Send video",
"Link video (TikTok, YouTube…) — dán link đầy đủ bắt đầu bằng https://": "Video link (TikTok, YouTube…) — paste the full link starting with https://",
"Số view hiện tại:": "Current views:",
"Ghi chú:": "Note:",
"Video của bạn": "Your videos",
"Bạn chưa gửi video nào.": "You haven't sent any videos yet.",
"Đã duyệt": "Approved",
"Từ chối": "Rejected",
"Chờ duyệt": "Pending",
"Báo view mới": "Report new views",
"Link video không đúng — dán link đầy đủ bắt đầu bằng https://": "Invalid video link — paste the full link starting with https://",
"Đang gửi…": "Sending…",
"✓ Đã gửi — admin duyệt xong sẽ cộng 💎 vào tài khoản.": "✓ Sent — once an admin approves it, 💎 is added to your account.",
"Nhập số view đang hiện trên video.": "Enter the view count shown on the video.",
"✓ Đã báo — admin duyệt xong sẽ cộng 💎 cho phần view mới.": "✓ Reported — once an admin approves it, 💎 is added for the new views.",
"🎟 Nhập mã": "🎟 Enter code",
"Mã tặng máy (12 ký tự) → nhận 1 máy miễn phí.\nMã chia sẻ / chuyển nhượng máy (8 ký tự) → máy hiện trong danh sách của bạn.\nMã GIẢM GIÁ thì nhập ở ô 🏷️ khi thuê / gia hạn / nâng cấp.": "Phone gift code (12 characters) → get 1 free phone.\nPhone share / transfer code (8 characters) → the phone shows up in your list.\nDISCOUNT codes go in the 🏷️ box when renting / renewing / upgrading.",
"Nhận": "Redeem",
"Nhập mã tặng máy (12 ký tự) hoặc mã chia sẻ / chuyển nhượng (8 ký tự).": "Enter a phone gift code (12 characters) or a share / transfer code (8 characters).",
"Đang kiểm tra…": "Checking…",
" Mã của bạn vẫn còn nguyên — thử lại sau.": " Your code is still unused — try again later.",
"Thuê điện thoại đám mây": "Rent a cloud phone",
"Đang tải bảng giá…": "Loading prices…",
". Vui lòng quay lại sau.": ". Please come back later.",
"Hệ thống đang bảo trì": "The system is under maintenance",
"⚠ Đang bật BẢO TRÌ — khách không thuê được. Tài khoản admin vẫn thuê được (không giới hạn chỗ trống) để thử máy.": "⚠ MAINTENANCE is on — customers can't rent. Admin accounts can still rent (no capacity limit) to test phones.",
"Chọn hệ điều hành": "Choose the OS",
"Chưa chắc thì chọn Android 9 — ổn định, chạy được nhiều app nhất.": "Not sure? Pick Android 9 — stable and runs the most apps.",
"💡 Android 15 không vào được Google / Play Store? Chọn Android 12 — máy đang thuê thì dùng Khác ▾ → Đổi Android (giữ nguyên hạn).": "💡 Android 15 can't get into Google / Play Store? Pick Android 12 — for a phone you're renting, use More ▾ → Switch Android (expiry is kept).",
"Chọn gói": "Choose a plan",
"Bấm 1 gói để xem giá — muốn khác thì mở ⚙️ Tự chỉnh ở dưới.": "Click a plan to see the price — for something else, open ⚙️ Custom below.",
"Cấu hình máy": "Phone setup",
"Cấu hình máy dùng thử": "Trial phone setup",
"Cấu hình máy miễn phí": "Free phone setup",
"Chọn RAM · CPU · FPS cho máy.": "Choose RAM · CPU · FPS for the phone.",
"CPU (nhân)": "CPU (cores)",
"💡 Treo game 1 tab: nên chọn từ 4GB RAM · 4 nhân (vào trận game đã dùng khoảng 2GB RAM) — 3GB · 2 nhân dễ giật. Treo 2–4 tab: 8GB · 8 nhân.": "💡 Idling 1 game tab: pick at least 4GB RAM · 4 cores (a game match already uses about 2GB RAM) — 3GB · 2 cores tends to stutter. 2–4 tabs: 8GB · 8 cores.",
"Độ phân giải": "Resolution",
"FPS (khung hình / giây)": "FPS (frames / second)",
"Số ngày & số máy": "Days & phones",
"Số ngày thuê": "Rental days",
"Số ngày": "Days",
"  khác:": "  other:",
"Số lượng máy": "Number of phones",
"Mã giảm giá · Blue": "Discount code · Blue",
"Máy mới tinh, không dính dữ liệu hay tài khoản Gmail của ai. Hết hạn máy tạm dừng — gia hạn trong 30 phút, quá thời gian máy và dữ liệu bị xoá.": "Brand-new phone, no one else's data or Gmail account. When it expires the phone pauses — renew within 30 minutes, or the phone and its data are deleted.",
"Huỷ": "Cancel",
"Thuê ngay": "Rent now",
"Hệ thống đang bảo trì, vui lòng quay lại sau.": "The system is under maintenance — please come back later.",
"Máy chủ điện thoại đang tạm ngưng, vui lòng quay lại sau.": "The phone servers are paused — please come back later.",
"Hãy chọn hệ điều hành (bản Android).": "Choose the OS (Android version).",
"⚙️ Tự chỉnh cấu hình": "⚙️ Custom setup",
"máy chủ đang bảo trì": "server under maintenance",
"hết chỗ cho cấu hình này": "no room for this setup",
"Số dư: ": "Balance: ",
"Chưa chọn gói": "No plan chosen",
"Bấm 1 gói ở bước 2 để xem giá.": "Click a plan in step 2 to see the price.",
"Chọn gói trước": "Choose a plan first",
"★ Máy dùng thử": "★ Trial phone",
"★ Máy miễn phí": "★ Free phone",
"⚙️ Cấu hình tự chọn": "⚙️ Custom setup",
"Số dư không đủ — cần nạp thêm ": "Not enough balance — top up ",
"⚠ Cấu hình này chưa đủ chơi game 3D (cần tối thiểu 4GB · 4 nhân) — hợp treo app, game nhẹ.": "⚠ This setup isn't enough for 3D games (needs at least 4GB · 4 cores) — fine for idle apps and light games.",
"Nhận máy miễn phí": "Get free phone",
"💎 Thuê bằng Blue": "💎 Rent with Blue",
"Xác nhận thuê máy": "Confirm rental",
"\n\nMáy miễn phí — không trừ tiền.": "\n\nFree phone — free of charge.",
"Đang tạo đơn…": "Creating the order…",
"Đã tạo đơn!": "Order created!",
" máy!": " phones!",
"Đã tạo đơn ": "Created order for ",
" Máy đang khởi tạo (khoảng 2–3 phút) — danh sách tự cập nhật khi máy chạy.": " The phone is being set up (about 2–3 minutes) — the list updates by itself when it's running.",
"Gia hạn ": "Renew ",
"máy": "phone",
"Đang tải giá…": "Loading price…",
"Máy": "Phone",
"Gia hạn thêm": "Renew for",
"Số ngày khác:": "Other days:",
"Gia hạn": "Renew",
"Nạp tiền": "Top up",
"Đang gia hạn…": "Renewing…",
"Nạp tiền vào tài khoản": "Top up your account",
"Số dư hiện tại: ": "Current balance: ",
"Số tiền nạp": "Top-up amount",
"Số khác:": "Other amount:",
"Chuyển khoản ngân hàng: quét mã QR bằng app ngân hàng bất kỳ, tiền tự cộng vào số dư sau khoảng 1 phút.": "Bank transfer: scan the QR code with any banking app; the money is added to your balance in about 1 minute.",
"Nạp bằng USDT / LTC trên web ↗": "Top up with USDT / LTC on the website ↗",
"Tạo mã chuyển khoản": "Create transfer code",
"Shop chưa cài tài khoản ngân hàng — tạm thời nạp trên web.": "The shop hasn't set up a bank account yet — top up on the website for now.",
"💰 Nạp 1 lần — nhận 1 mã giảm giá cloud phone": "💰 Top up once — get 1 cloud phone discount code",
"Bạn đã nhận mã của đợt này rồi.": "You've already got this round's code.",
"Mã của bạn: ": "Your code: ",
"Bạn đã dùng thử 1 máy rồi.": "You've already used 1 trial phone.",
"Số tiền tối thiểu là ": "The minimum amount is ",
"Đang tạo mã…": "Creating the code…",
"Chuyển khoản ": "Transfer ",
"Không tạo được mã QR —\nchuyển khoản theo thông tin bên cạnh": "Couldn't create the QR code —\ntransfer using the details beside it",
"Ngân hàng": "Bank",
"Số tài khoản": "Account number",
"Chủ tài khoản": "Account holder",
"Số tiền": "Amount",
"Nội dung chuyển khoản (ghi ĐÚNG)": "Transfer note (type it EXACTLY)",
"Mở app ngân hàng → Quét mã QR: số tiền và nội dung tự điền. Chuyển tay thì ghi đúng nội dung ở trên, nếu không tiền sẽ không tự cộng. Mã có hiệu lực 20 phút.": "Open your banking app → scan the QR code: the amount and note fill in by themselves. If you transfer by hand, type the note above exactly or the money won't be added automatically. The code is valid for 20 minutes.",
"⏳ Đang chờ ngân hàng báo có… (tự kiểm tra, không cần bấm gì)": "⏳ Waiting for the bank to confirm… (checks by itself, nothing to click)",
"Mã nạp này đã hết hạn. Nếu bạn đã chuyển tiền mà chưa được cộng, liên hệ hỗ trợ kèm nội dung chuyển khoản.": "This top-up code has expired. If you transferred money and it wasn't added, contact support with the transfer note.",
"Chưa thấy tiền về. Nếu đã chuyển đúng nội dung mà quá 15 phút chưa cộng, liên hệ hỗ trợ kèm nội dung chuyển khoản.": "No money received yet. If you used the exact note and it's still not added after 15 minutes, contact support with the transfer note.",
"Mã này là mã riêng của tài khoản khác — chỉ tài khoản được tặng mới dùng được.": "This code belongs to another account — only the account it was gifted to can use it.",
"Hôm nay bạn đã dùng đủ số mã giảm giá cho phép — mai dùng tiếp nhé.": "You've used today's discount code limit — use more tomorrow.",
"Máy chủ chưa bật nút thử lại — nhắn shop để được tạo lại máy.": "The server hasn't enabled the retry button — message the shop to have the phone recreated.",
"Bạn đã hết lượt quay — nạp thêm để nhận lượt mới.": "You're out of spins — top up to get new ones.",
"Vòng quay chưa bắt đầu.": "The wheel hasn't started yet.",
"Chương trình vòng quay đã kết thúc.": "The wheel event has ended.",
"Vòng quay đang tạm tắt.": "The wheel is paused for now.",
"Vòng quay đã hết giải.": "The wheel is out of prizes.",
"Hiện không bán thêm lượt quay.": "Extra spins aren't on sale right now.",
"Giá quay thêm vừa thay đổi — xem lại giá rồi bấm lại.": "The extra-spin price just changed — check it and click again.",
"Nạp từ 100.000đ trong chương trình để được quay thêm.": "Top up from 100,000đ during the event to buy extra spins.",
"Hôm nay bạn đã mua đủ số lượt quay thêm — mai quay tiếp nhé.": "You've bought today's limit of extra spins — spin again tomorrow.",
"Điều kiện mua lượt / vé vừa đổi — xem lại rồi bấm lại.": "The conditions for buying spins / tickets just changed — check them and click again.",
"Hiện không bán vé may mắn.": "Lucky tickets aren't on sale right now.",
"Xem giải": "See prizes",
"🎡 Mở vòng quay": "🎡 Open the wheel",
"Đang tải vòng quay…": "Loading the wheel…",
"Vòng quay chưa mở — quay lại sau nhé.": "The wheel isn't open — come back later.",
"Vòng quay may mắn": "Lucky wheel",
"📜 Thể lệ  ▸": "📜 Rules  ▸",
"Chương trình đã kết thúc. Mã đã trúng vẫn dùng được đến hết hạn.": "The event has ended. Codes you won still work until they expire.",
"Vòng quay đang tạm tắt. Mã đã trúng vẫn dùng được đến hết hạn.": "The wheel is paused. Codes you won still work until they expire.",
"Dùng vé": "Use ticket",
"Đang quay…": "Spinning…",
"Vòng quay đang tạm tắt": "The wheel is paused",
"Chương trình đã kết thúc": "The event has ended",
"Hôm nay đã mua đủ lượt — nạp thêm để nhận lượt mới": "Today's spin limit reached — top up to get new spins",
"Số dư chưa đủ": "Not enough balance",
" và 🍀 vé may mắn": " and 🍀 lucky tickets",
"Quay thêm 1 lượt?": "One more spin?",
"Mua 1 lượt quay?": "Buy 1 spin?",
"Vé may mắn": "Lucky ticket",
"Hôm nay bạn đã mua đủ số lượt / vé — mai quay tiếp nhé.": "You've bought today's limit of spins / tickets — spin again tomorrow.",
"🍀 Dùng 1 vé may mắn?": "🍀 Use 1 lucky ticket?",
"HẾT": "GONE",
"📖 Hướng dẫn chơi": "📖 How to play",
"Bấm QUAY": "Click SPIN",
"Đang quay, số trên vòng ẩn hết. Kim dừng là hộp quà nổ ra mã của bạn.": "While it spins the numbers are hidden. When the pointer stops, the gift box pops open with your code.",
"Dùng mã khi thanh toán": "Use the code at checkout",
"Hết lượt miễn phí vẫn quay tiếp được.": "You can keep spinning after your free spins run out.",
" Luôn hỏi lại trước khi trừ tiền.": " Always asks before charging.",
". Vòng đổi sang mặt vé riêng, trừ vào số dư, luôn hỏi lại trước khi trừ.": ". The wheel switches to its own ticket face, charged to your balance, always asking before charging.",
"🌐 Chơi được cả trên web (vòng quay ngay trang chủ) và app Android (bản tải từ web). Lượt quay, vé và mã dùng chung cho cả tài khoản.": "🌐 Also playable on the web (wheel on the home page) and the Android app (the version from the website). Spins, tickets and codes are shared across your account.",
"🎟 Mã của tôi": "🎟 My codes",
"Mã bạn quay trúng sẽ nằm ở đây.": "Codes you win will show up here.",
"  ·  🤝 tặng bạn bè được": "  ·  🤝 can be gifted to friends",
"📜 Thể lệ  ": "📜 Rules  ",
" đến khi có thông báo kết thúc.": " until an end is announced.",
" và vé may mắn": " and lucky tickets",
"giữ dùng sau hoặc tặng bạn bè dùng đều được": "keep it for later or gift it to a friend",
"chỉ tài khoản quay trúng dùng được": "only the winning account can use it",
"🎲 Kết quả quay hoàn toàn ngẫu nhiên do máy chủ quyết định. Mỗi ô có tỷ lệ trúng khác nhau — giải càng lớn càng hiếm. Giải có số lượng giới hạn; ô ghi HẾT là đã có người trúng hết.": "🎲 Spin results are fully random, decided by the server. Each slice has different odds — the bigger the prize, the rarer. Prizes are limited; a slice marked GONE has been fully won.",
"Không giới hạn": "Unlimited",
"🎁 Chúc mừng!": "🎁 Congratulations!",
" 🍀 Vé may mắn ": " 🍀 Lucky ticket ",
"Chúc mừng! Bạn nhận được": "Congratulations! You got",
"mã giảm giá": "discount code",
"Chép mã": "Copy code",
"chỉ tài khoản của bạn dùng được": "only your account can use it",
". Nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn máy.": ". Enter it in the 🏷️ Discount code box when renting / renewing a phone.",
"✓ Đã chép": "✓ Copied",
"Nâng cấp ": "Upgrade ",
"RAM đã tối đa.": "RAM is already at the maximum.",
"CPU đã tối đa.": "CPU is already at the maximum.",
"Mã giảm giá": "Discount code",
"Máy tự khởi động lại khoảng 1 phút để nhận cấu hình mới — app và dữ liệu giữ nguyên. Các lần gia hạn sau tính theo cấu hình mới.": "The phone restarts for about 1 minute to apply the new setup — apps and data are kept. Future renewals are priced on the new setup.",
"Nâng cấp ngay": "Upgrade now",
"Chọn RAM hoặc CPU muốn nâng.": "Choose the RAM or CPU to upgrade.",
"Nâng cấp": "Upgrade",
"\nMáy sẽ tự khởi động lại khoảng 1 phút.": "\nThe phone will restart for about 1 minute.",
"Đang nâng cấp…": "Upgrading…",
"Đổi Android — ": "Switch Android — ",
"Chưa có bản Android nào khác để đổi.": "There's no other Android version to switch to yet.",
"Đổi sang": "Switch to",
"⚠ Đổi hệ điều hành sẽ XOÁ SẠCH toàn bộ dữ liệu trong máy: app, game, tài khoản đã đăng nhập, ảnh, file — không khôi phục được.": "⚠ Switching the OS WIPES all data on the phone: apps, games, signed-in accounts, photos, files — it can't be recovered.",
"Bấm Đổi là máy cũ bị XOÁ NGAY (không mở được nữa), xoá xong mới tạo máy mới — khoảng 2–5 phút. Máy mới miễn phí, giữ nguyên hạn dùng.": "Clicking Switch DELETES the old phone right away (it can't be opened anymore), then creates the new one — about 2–5 minutes. The new phone is free and keeps the same expiry.",
"Tôi hiểu, toàn bộ dữ liệu trong máy sẽ bị xoá": "I understand all data on the phone will be deleted",
"Đổi": "Switch",
"\nLưu ý: có khách báo Android 15 không vào được Google / Play Store — cần Google thì chọn Android 12.": "\nNote: some customers report Android 15 can't get into Google / Play Store — if you need Google, pick Android 12.",
"tiết kiệm nhất": "lightest",
"mạng yếu": "weak network",
"cân bằng": "balanced",
"mượt": "smooth",
"rất mượt": "very smooth",
"Đổi FPS — ": "Change FPS — ",
"Số khung hình mỗi giây": "Frames per second",
"FPS càng cao hình càng mượt nhưng máy chạy nặng hơn và tốn mạng hơn. Treo game cả ngày nên để 30 FPS (mạng yếu: 20 FPS).": "Higher FPS looks smoother but works the phone harder and uses more data. For all-day game idling, use 30 FPS (weak network: 20 FPS).",
" Máy dưới 4 nhân chọn tối đa 60 FPS.": " Phones with fewer than 4 cores go up to 60 FPS.",
"✔ Không tạo máy mới · không mất dữ liệu · không tốn tiền.": "✔ No new phone · no data lost · free of charge.",
"Lưu": "Save",
"Đang lưu…": "Saving…",
"Chọn số FPS khác để đổi": "Pick a different FPS to change",
"Hình truyền về đổi ngay ở lần mở máy kế tiếp.": "The streamed picture changes the next time you open the phone.",
"Để FPS mới có tác dụng BÊN TRONG GAME, máy cần khởi động lại 1 lần (khoảng 1–2 phút). App đang mở trong máy sẽ tắt, dữ liệu giữ nguyên. Chưa tiện thì để sau — lần máy bật lại kế tiếp sẽ tự áp dụng.": "For the new FPS to apply INSIDE GAMES, the phone needs to restart once (about 1–2 minutes). Apps open on the phone will close; your data is kept. If now isn't a good time, do it later — it applies automatically the next time the phone starts.",
"Để sau": "Later",
"⚡ Khởi động lại ngay": "⚡ Restart now",
"Đang khởi động lại máy… (1–2 phút, có thể đóng hộp này)": "Restarting the phone… (1–2 minutes, you can close this box)",
"Máy đang khởi động lại — khoảng 1–2 phút.": "The phone is restarting — about 1–2 minutes.",
"Giao diện": "Appearance",
"🔍 Cỡ chữ của app": "🔍 App text size",
"Chữ mẫu: Máy 6GB · 6 nhân · 60 FPS": "Sample text: Phone 6GB · 6 cores · 60 FPS",
"Kéo sang phải cho chữ TO hơn, sang trái cho NHỎ hơn rồi bấm Áp dụng. App sẽ tự mở lại cửa sổ danh sách với cỡ mới — các cửa sổ máy đang mở không bị đóng.": "Drag right for BIGGER text, left for SMALLER, then click Apply. The app reopens the list window at the new size — open phone windows aren't closed.",
"Hiện ô ưu đãi · vòng quay ở đầu danh sách máy": "Show the deals · wheel box at the top of the phone list",
"Mặc định 100%": "Default 100%",
" (mặc định)": " (default)",
"Máy chủ của máy này chưa có tính năng này — đang được cập nhật, thử lại sau.": "This phone's server doesn't have this feature yet — it's being updated, try again later.",
"Màn hình": "Screen",
"Cài app": "Install app",
"Ứng dụng": "Apps",
"Khác": "More",
"Công cụ — ": "Tools — ",
"Làm mới": "Refresh",
"Xoay màn": "Rotate screen",
"Khoá màn máy NGANG hoặc DỌC (giữ luôn cả khi tắt app). Game chỉ chạy màn ngang vẫn tự xoay ngang. Cửa sổ máy trên máy tính tự xoay theo — không phải nghiêng đầu.": "Lock the phone to LANDSCAPE or PORTRAIT (kept even after closing the app). Landscape-only games still rotate to landscape. The phone window on your PC rotates to match — no need to tilt your head.",
"▭  Màn ngang": "▭  Landscape",
"▯  Màn dọc": "▯  Portrait",
"Độ rộng nhỏ nhất (Smallest width)": "Smallest width",
"Như \"Độ rộng nhỏ nhất\" trong Tuỳ chọn nhà phát triển của Android: số càng LỚN thì chữ, biểu tượng, cửa sổ app càng NHỎ — màn chứa được nhiều hơn (VD xếp nhiều tab clone). Số càng nhỏ thì mọi thứ càng to.": "Like \"Smallest width\" in Android's Developer options: the BIGGER the number, the SMALLER text, icons and app windows get — more fits on screen (e.g. many clone tabs). The smaller the number, the bigger everything is.",
"Đang đọc màn hình máy…": "Reading the phone's screen…",
"Số khác (240 – 1600):": "Other value (240 – 1600):",
"Đặt": "Set",
"Trả về mặc định": "Reset to default",
"Đã khoá màn NGANG.": "Locked to LANDSCAPE.",
"Đã khoá màn DỌC.": "Locked to PORTRAIT.",
" App / game hỗ trợ ngang sẽ hiện ngang; app chỉ chạy màn dọc thì vẫn dọc.": " Apps / games that support landscape show in landscape; portrait-only apps stay portrait.",
"Nhập số từ 240 đến 1600 (dp).": "Enter a number from 240 to 1600 (dp).",
"Đang trả về mặc định…": "Resetting to default…",
"Đã đổi.": "Changed.",
"Cài app / chép file vào máy": "Install apps / copy files to the phone",
"File .apk / .apks / .xapk / .apkm → cài vào máy. File khác (ảnh, video, tài liệu…) → chép vào thư mục Download của máy.": ".apk / .apks / .xapk / .apkm files → installed on the phone. Other files (photos, videos, documents…) → copied to the phone's Download folder.",
"Chọn file trên máy tính…": "Choose a file on your PC…",
"Cài từ link": "Install from link",
"Link tải trực tiếp file (thường kết thúc bằng .apk), không phải link trang web.": "A direct download link to the file (usually ending in .apk), not a web page link.",
"Chọn file để cài / chép vào máy": "Choose a file to install / copy to the phone",
"Tất cả file": "All files",
"File lớn hơn 4GB — không gửi được.": "The file is larger than 4GB — can't send it.",
"Link phải bắt đầu bằng http:// hoặc https://": "The link must start with http:// or https://",
"Máy chủ chưa nhận việc — thử lại.": "The server didn't take the task — try again.",
"Đang cài / chép vào máy…": "Installing / copying to the phone…",
"Đang đọc danh sách app trong máy…": "Reading the phone's app list…",
"Ứng dụng trong máy": "Apps on the phone",
"App bạn đã cài (không gồm app hệ thống). Mở = mở toàn màn hình (game cần màn ngang tự xoay ngang).": "Apps you installed (system apps not included). Open = open full screen (landscape games rotate by themselves).",
"Máy chưa có app nào do bạn cài. Cài ở thẻ Cài app, hoặc từ CH Play trong máy.": "No apps you installed yet. Install them in the Install app tab, or from Play Store on the phone.",
"Mở": "Open",
"Dừng": "Stop",
"Xoá dữ liệu": "Clear data",
"Gỡ": "Uninstall",
"Xoá dữ liệu app": "Clear app data",
"Gỡ app": "Uninstall app",
"mở": "open",
"dừng": "stop",
"xoá dữ liệu": "clear data",
"gỡ": "uninstall",
"Clone tab — chạy thêm bản 2, 3… của 1 app để đăng nhập acc khác": "Clone tabs — run a 2nd, 3rd… copy of an app to sign in to other accounts",
"Mỗi bản clone là 1 hồ sơ riêng của Android, dùng đúng app gốc đã cài trong máy. Bản clone hiện thành biểu tượng \"Clone 1, 2…\" (hoặc tab Công việc) trên màn hình chính, hoặc bấm Mở bản ở đây — mở toàn màn hình, game ngang tự xoay ngang. Mỗi bản cần thêm RAM / CPU.": "Each clone is a separate Android profile using the original app already installed on the phone. Clones show up as \"Clone 1, 2…\" icons (or a Work tab) on the home screen, or click Open copy here — opens full screen, landscape games rotate by themselves. Each copy needs extra RAM / CPU.",
"Máy chưa có app nào. Cài app trước (VD game từ CH Play trong máy, hoặc file APK ở thẻ Cài app) rồi bấm Làm mới.": "No apps on the phone yet. Install one first (e.g. a game from Play Store on the phone, or an APK in the Install app tab), then click Refresh.",
"App cần clone": "App to clone",
"Bỏ clone": "Remove clones",
"Đang bỏ các bản clone…": "Removing the clones…",
"Đã bỏ các bản clone.": "Clones removed.",
"Mở link trên máy": "Open a link on the phone",
"Mở trên máy": "Open on phone",
"Vị trí GPS giả (máy Android 12 trở lên)": "Fake GPS location (Android 12 and up)",
"Nhập toạ độ dạng: vĩ độ, kinh độ — trên Google Maps bấm chuột phải vào 1 điểm rồi bấm dòng số để copy. VD Hà Nội: 21.0285, 105.8542": "Enter coordinates as: latitude, longitude — on Google Maps, right-click a spot, then click the numbers to copy them. E.g. Hanoi: 21.0285, 105.8542",
"Đặt vị trí": "Set location",
"Tắt": "Off",
"Chụp màn hình": "Screenshot",
"Nút nguồn (tắt / mở màn)": "Power button (screen off / on)",
"⟳  Khởi động lại máy": "⟳  Restart phone",
"Đang mở…": "Opening…",
"✓ Đã mở trên máy.": "✓ Opened on the phone.",
"Đang tắt vị trí giả…": "Turning off the fake location…",
"Đã tắt vị trí giả.": "Fake location turned off.",
"Nhập dạng: 21.0285, 105.8542": "Format: 21.0285, 105.8542",
"Toạ độ không hợp lệ (vĩ độ −90 … 90, kinh độ −180 … 180).": "Invalid coordinates (latitude −90 … 90, longitude −180 … 180).",
"Đang đặt vị trí…": "Setting the location…",
"Đã đặt vị trí.": "Location set.",
"Không chụp được màn hình.": "Couldn't take a screenshot.",
"Đang bấm nút nguồn…": "Pressing the power button…",
"✓ Đã bấm nút nguồn — màn đang tắt thì bật lên, đang bật thì tắt.": "✓ Pressed the power button — the screen turns on if it was off, off if it was on.",
"Máy chủ tải từ trang chính chủ (Termux: GitHub · MT Manager: mt.cc · ZArchiver: zdevs.ru) rồi cài vào máy. Lần đầu mất vài chục giây, máy sau cài ngay.": "The server downloads from the official sites (Termux: GitHub · MT Manager: mt.cc · ZArchiver: zdevs.ru) and installs it on the phone. The first time takes a few dozen seconds; later phones install instantly.",
"Cần root cho Termux / MT Manager → thẻ Root, bật cho app đó.": "Need root for Termux / MT Manager → Root tab, turn it on for that app.",
"✗ Không mở được kho: ": "✗ Couldn't open the app store: ",
"Máy chủ chưa cập nhật bản có Kho app — báo admin cập nhật.": "The server doesn't have the App store version yet — ask the admin to update.",
"Cài lại": "Reinstall",
"Cài": "Install",
"   ✓ Đã cài": "   ✓ Installed",
"Đang cài app khác — đợi xong rồi bấm tiếp.": "Installing another app — wait until it's done, then click again.",
"Chỉ app được bật bên dưới mới dùng được lệnh su (vd Termux). App khác xin root sẽ bị từ chối và hiện ở mục \"Vừa xin root\".": "Only apps turned on below can use su (e.g. Termux). Other apps asking for root are denied and show up under \"Recently asked for root\".",
"  Bật root cho máy này": "  Turn on root for this phone",
"Đang đọc…": "Reading…",
"Một số game và app có thể phát hiện máy đã root. Chỉ bật cho app thật sự cần.": "Some games and apps can detect a rooted phone. Only turn it on for apps that really need it.",
"Đọc lại": "Reload",
"Máy chủ chưa có tính năng này — báo admin cập nhật.": "The server doesn't have this feature yet — ask the admin to update.",
"✗ Không đọc được: ": "✗ Couldn't read: ",
"Vừa xin root (chưa được bật)": "Recently asked for root (not on yet)",
"  ·  xin lúc ": "  ·  asked at ",
"Chưa có app nào do bạn cài. Cài app (vd Termux) rồi bấm Đọc lại.": "No apps you installed yet. Install one (e.g. Termux), then click Reload.",
"⚠ Máy đang bật SELinux Enforcing — root theo app có thể chưa dùng được. Báo hỗ trợ nếu app vẫn báo không có su.": "⚠ The phone has SELinux Enforcing on — per-app root may not work yet. Contact support if the app still says su isn't available.",
"Máy đang tắt hoặc mất kết nối — vẫn lưu được, máy bật lên tự áp dụng.": "The phone is off or disconnected — you can still save; it applies when the phone starts.",
"Máy chưa bật root gốc — bấm Lưu: máy tự khởi động lại khoảng 1 phút để bật root, rồi cài cho app đã chọn.": "The phone doesn't have base root on yet — click Save: the phone restarts for about 1 minute to turn on root, then sets it up for the chosen apps.",
"Bấm Lưu để bật root.": "Click Save to turn on root.",
"Bấm Lưu để tắt root.": "Click Save to turn off root.",
"Đã bật nhưng chưa chạy — bấm Lưu để chạy lại.": "On but not running — click Save to run it again.",
"Đang tắt — không app nào dùng được lệnh su.": "Off — no app can use su.",
"Chưa chọn app nào — bật root nhưng mọi app xin root sẽ bị từ chối. Vẫn lưu?": "No app selected — root will be on but every app asking for root will be denied. Save anyway?",
"Đang lưu cấu hình root…": "Saving the root settings…",
"Đang bật root — máy khởi động lại khoảng 1 phút…": "Turning on root — the phone restarts for about 1 minute…",
"Đã lưu.": "Saved.",
"Khởi động lại": "Restart",
"Đang khởi động lại máy (1–3 phút)…": "Restarting the phone (1–3 minutes)…",
"Mã không đúng hoặc đã bị tắt.": "Wrong code, or it has been disabled.",
"Mã đã hết hạn.": "The code has expired.",
"Mã chưa đến ngày sử dụng.": "The code isn't valid yet.",
"Mã đã hết lượt sử dụng.": "The code has no uses left.",
"Bạn đã dùng hết số lượt của mã này.": "You've used up your uses of this code.",
"Mã này không áp dụng cho loại đơn này.": "This code doesn't apply to this kind of order.",
"Đơn chưa đạt giá trị tối thiểu để dùng mã này.": "The order doesn't reach the minimum for this code.",
"Bạn nhập sai mã quá nhiều lần — thử lại sau 10 phút.": "Too many wrong codes — try again in 10 minutes.",
"Đây là mã TẶNG MÁY — nhập ở nút 🎟 Nhập mã trên danh sách máy (không dùng khi thanh toán).": "This is a PHONE GIFT code — enter it with the 🎟 Enter code button on the phone list (not at checkout).",
"Đây là mã giảm giá — nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn / nâng cấp máy.": "This is a discount code — enter it in the 🏷️ Discount code box when renting / renewing / upgrading.",
"Máy miễn phí không dùng mã giảm giá được.": "Free phones can't use discount codes.",
"Hãy nhập mã.": "Please enter a code.",
"Chọn cấu hình / số ngày trước rồi bấm Áp dụng.": "Choose the setup / days first, then click Apply.",
"Tính năng mã giảm giá chưa bật.": "Discount codes aren't enabled.",
"Mã không đúng, đã bị huỷ hoặc đã hết hạn.": "Wrong code, cancelled or expired.",
"Mã này đã có người dùng rồi.": "Someone has already used this code.",
"Đây là máy của chính bạn.": "This is your own phone.",
"Bạn đã được chia sẻ máy này rồi.": "This phone is already shared with you.",
"Hôm nay bạn đã điểm danh rồi — quay lại ngày mai nhé.": "You've already checked in today — come back tomorrow.",
"Mạng (wifi / 4G) này đã đủ số tài khoản nhận Blue hôm nay — mai thử lại nhé.": "This network (wifi / 4G) has reached today's limit of accounts earning Blue — try again tomorrow.",
"Nạp tiền ít nhất 1 lần để mở khoá trả bằng Blue (Blue vẫn được tích bình thường).": "Top up at least once to unlock paying with Blue (you still earn Blue as usual).",
"Bạn chưa có Blue để trả.": "You don't have any Blue to pay with yet.",
"Máy miễn phí không trả bằng Blue được.": "Free phones can't be paid with Blue.",
"Hôm nay bạn đã nhận nhiệm vụ này rồi.": "You've already claimed this mission today.",
"Chưa xong nhiệm vụ — làm xong rồi bấm nhận nhé.": "Mission not done yet — finish it, then claim.",
"Nhiệm vụ này đang tạm tắt.": "This mission is paused for now.",
"Nhiệm vụ không hợp lệ.": "Invalid mission.",
"Hôm nay bạn đã nhận đủ Blue tối đa — mai quay lại nhé.": "You've earned today's maximum Blue — come back tomorrow.",
"Blue của bạn đang được tạm giữ để kiểm tra — liên hệ hỗ trợ.": "Your Blue is on hold for a check — contact support.",
"Tài khoản mới — sau 24 giờ mới tích Blue được.": "New account — you can earn Blue after 24 hours.",
"Bị chặn: không được tự cộng tiền.": "Blocked: you can't add money to yourself.",
"Bị chặn.": "Blocked.",
"Số tiền quá lớn.": "The amount is too large.",
"⛔ Tài khoản đã bị cấm do vi phạm điều khoản sử dụng (gian lận / cày clone / lợi dụng lỗi). Nếu là nhầm lẫn, liên hệ hỗ trợ kèm tên đăng nhập.": "⛔ This account has been banned for breaking the terms of use (fraud / clone farming / exploiting bugs). If this is a mistake, contact support with your username.",
"Máy phải đang chạy mới đổi FPS được.": "The phone must be running to change FPS.",
"Vừa đổi FPS xong — đợi vài giây rồi đổi tiếp nhé.": "FPS was just changed — wait a few seconds before changing it again.",
"Máy chủ chưa bật tính năng đổi FPS — thử lại sau ít phút.": "The server hasn't enabled FPS changes yet — try again in a few minutes.",
"Máy đang được nâng cấp, đợi khoảng 1 phút rồi thử lại.": "The phone is being upgraded — wait about 1 minute and try again.",
"Máy miễn phí không nâng cấp được — thuê máy trả phí để nâng.": "Free phones can't be upgraded — rent a paid phone to upgrade.",
"Cấu hình nâng cấp không hợp lệ.": "Invalid upgrade setup.",
"Đã huỷ cập nhật.": "Update cancelled.",
"Mất mạng khi tải bản mới — kiểm tra mạng rồi thử lại.": "Lost the network while downloading the new version — check your network and try again.",
"File tải về chưa đủ — có thể web vừa lên bản mới hơn, thử lại.": "The download is incomplete — the website may have just released a newer version; try again.",
"File tải về không khớp mã kiểm tra — có thể web vừa lên bản mới hơn, thử lại.": "The download doesn't match its checksum — the website may have just released a newer version; try again.",
"File cập nhật bị hỏng — thử lại.": "The update file is corrupted — try again.",
"Gói cập nhật thiếu CloudBluePC.exe — báo hỗ trợ.": "The update package is missing CloudBluePC.exe — contact support.",
"Bản mới tải về không đầy đủ — mở lại app rồi cập nhật lại.": "The downloaded version is incomplete — reopen the app and update again.",
"Thư mục app có thêm file khác — không tự thay được. Tải bản mới trên web rồi giải nén đè.": "The app folder has other files in it — can't replace it automatically. Download the new version on the website and unzip it over the old one.",
"Chờ app cũ đóng…": "Waiting for the old app to close…",
"Đang đóng các cửa sổ máy đang mở…": "Closing open phone windows…",
"Đang thay bản mới…": "Replacing with the new version…",
"Không thay được thư mục app vì có chương trình khác đang mở file trong đó (cửa sổ cmd, phần mềm diệt virus…). Đã mở lại bản cũ — đóng chương trình đó rồi bấm cập nhật lại.": "Couldn't replace the app folder because another program has a file open in it (a cmd window, antivirus…). Reopened the old version — close that program and update again.",
"Đang chép bản mới…": "Copying the new version…",
"CloudBlue — đang cập nhật": "CloudBlue — updating",
"Đang cập nhật CloudBlue PC…": "Updating CloudBlue PC…",
"Xong — đang mở lại app…": "Done — reopening the app…",
"Cập nhật CloudBlue PC": "Update CloudBlue PC",
"Bấm Cập nhật ngay: app tự tải bản mới, đóng các cửa sổ máy đang mở, thay bản mới rồi tự mở lại (khoảng 1 phút). Tài khoản, máy và cài đặt giữ nguyên.": "Click Update now: the app downloads the new version, closes open phone windows, swaps in the new version and reopens (about 1 minute). Your account, phones and settings are kept.",
"App đang nằm chung thư mục với file khác (hoặc trong thư mục không được ghi) nên không tự thay được. Bấm Tải về → đóng app → giải nén file vừa tải đè lên thư mục app cũ → mở lại CloudBluePC.exe.": "The app shares its folder with other files (or sits in a folder it can't write to), so it can't replace itself. Click Download → close the app → unzip the downloaded file over the old app folder → reopen CloudBluePC.exe.",
"Cập nhật ngay": "Update now",
"Tải về": "Download",
"Tải bằng tay": "Download manually",
"Đang tải trong trình duyệt — tải xong: đóng app, giải nén đè lên thư mục app cũ, mở lại CloudBluePC.exe.": "Downloading in your browser — when it's done: close the app, unzip over the old app folder, reopen CloudBluePC.exe.",
"Đang huỷ…": "Cancelling…",
"Đang tải bản mới…": "Downloading the new version…",
"Đang mở trình cập nhật — app tự đóng rồi mở lại…": "Opening the updater — the app closes and reopens by itself…",
"Không mở được bản mới vừa tải (phần mềm diệt virus chặn?) — bấm Tải bằng tay.": "Couldn't open the version just downloaded (blocked by antivirus?) — click Download manually.",
"Thử lại": "Retry",
"Không tìm thấy máy này trong tài khoản.": "This phone isn't in your account.",
"Huỷ máy": "Cancel phone",
"Đang huỷ máy — máy sẽ biến mất khỏi danh sách trong ít phút.": "Cancelling the phone — it will disappear from the list in a few minutes.",
"Đã lưu cỡ chữ mới — đóng app rồi mở lại là thấy.": "New text size saved — close and reopen the app to see it.",
"🎁 Hiện ưu đãi · vòng quay  ▾": "🎁 Show deals · wheel  ▾",
"Ẩn ưu đãi  ▴": "Hide deals  ▴",
"Xoay màn · Độ rộng nhỏ nhất…": "Rotate screen · Smallest width…",
"Cài app (APK / link)…": "Install app (APK / link)…",
"Ứng dụng trong máy…": "Apps on the phone…",
"Khác: mở link, GPS, chụp màn…": "More: open link, GPS, screenshot…",
"Nâng cấp RAM / CPU": "Upgrade RAM / CPU",
"Đang đổi Android… (chờ máy mới)": "Switching Android… (waiting for the new phone)",
"Đổi Android (9 / 12 / 15)…": "Switch Android (9 / 12 / 15)…",
"Huỷ máy (xoá vĩnh viễn)": "Cancel phone (delete permanently)",
"Điện thoại đám mây — điều khiển trên máy tính": "Cloud phones — control them from your PC",
"Mật khẩu": "Password",
"Nhập email và mật khẩu.": "Enter your email and password.",
"Đang đăng nhập…": "Logging in…",
"Đăng nhập": "Log in",
"Chưa có tài khoản? Đăng ký trên web  ↗": "No account yet? Sign up on the website  ↗",
"Máy của tôi": "My phones",
"Đăng xuất": "Log out",
"⟳ Làm mới": "⟳ Refresh",
"🎨 Giao diện": "🎨 Appearance",
"Mở web ↗": "Open website ↗",
"Số dư": "Balance",
"+ Thuê máy": "+ Rent a phone",
"🎉 Mới: Tích Blue": "🎉 New: Earn Blue",
"Tích Blue để thuê / gia hạn máy rẻ hơn — 1 Blue = 1đ. Cách nhận:\n\n": "Earn Blue to rent / renew phones for less — 1 Blue = 1đ. How to earn:\n\n",
"\n\nMở Tích Blue để điểm danh ngay?": "\n\nOpen Earn Blue to check in now?",
"Làm video về CloudBlue trên TikTok, YouTube… view càng tăng 💎 càng nhiều.": "Make videos about CloudBlue on TikTok, YouTube… more views, more 💎.",
"Ưu đãi cloud phone": "Cloud phone deals",
"Đã xếp lại lệnh tạo máy — máy mới sẽ có sau ít phút. Hạn dùng của bạn vẫn giữ nguyên.": "Phone creation re-queued — the new phone will be ready in a few minutes. Your expiry is kept.",
"⬇ Cập nhật ngay": "⬇ Update now",
"Tải bản mới nhất mới dùng tiếp được. ": "Download the latest version to keep using the app. ",
"Tài khoản và máy của bạn giữ nguyên.": "Your account and phones are kept.",
"Cập nhật": "Update",
"Bấm Cập nhật: app tự tải, thay bản mới rồi tự mở lại — tài khoản giữ nguyên.": "Click Update: the app downloads it, swaps in the new version and reopens — your account is kept.",
"Bấm Cập nhật để xem cách tải bản mới.": "Click Update to see how to get the new version.",
"Cần cập nhật app để dùng tiếp": "Update the app to keep using it",
"Bấm ⬇ Cập nhật ngay ở dải đỏ phía trên — app tự tải, thay bản mới và mở lại.": "Click ⬇ Update now in the red bar above — the app downloads it, swaps in the new version and reopens.",
"Bạn chưa có máy nào.": "You don't have any phones yet.",
"Thuê máy ngay trong app — chọn cấu hình, thanh toán bằng số dư.": "Rent a phone right in the app — pick a setup and pay from your balance.",
" · được chia sẻ": " · shared",
"🔁 Thử tạo lại máy": "🔁 Try recreating the phone",
"🔄 Đang đổi Android: máy mới đang tạo, máy này vẫn dùng được tới lúc đó rồi tự xoá.": "🔄 Switching Android: the new phone is being created; this one keeps working until then and is then deleted.",
"▶  Điều khiển": "▶  Control",
"Khác ▾": "More ▾",
"Đang khởi động lại máy — chờ khoảng 1 phút rồi mở lại.": "Restarting the phone — wait about 1 minute, then open it again.",
"Ổn định": "Stable",
"phổ biến": "popular",
"Xoay": "Rotate",
"Kho app": "App store",
"Root theo app": "Per-app root",
"Root theo app…": "Per-app root…",
"Treo 2–4 tab game": "2–4 game tabs",
"treo game": "idling",
"Quay": "Spin",
"QUAY": "SPIN",
"Xong": "Done",
"Xong.": "Done.",
"⚠️ Hệ thống đang bảo trì nên tạm thời chưa đăng nhập / tải dữ liệu được. Vui lòng thử lại sau ít phút.": "⚠️ The system is under maintenance, so signing in and loading data are paused. Please try again in a few minutes.",
"\n🔒 Nạp tiền ít nhất 1 lần để mở khoá trả bằng Blue (vẫn tích bình thường).": "\n🔒 Top up at least once to unlock paying with Blue (you still earn it as usual).",
"   ·   Android — vượt trần": "   ·   Android — over the limit",
"1 Blue = 1đ khi thuê / gia hạn điện thoại đám mây — bật 💎 Trả bằng Blue lúc thanh toán.": "1 Blue = 1đ when renting / renewing cloud phones — turn on 💎 Pay with Blue at checkout.",
"Chưa kiểm tra được mã, thử lại. Sửa hoặc xoá mã giảm giá để thanh toán.": "Couldn't check the code — try again. Edit or remove the discount code to pay.",
"FPS càng cao hình càng mượt nhưng máy chạy nặng hơn và tốn mạng hơn. Treo game cả ngày nên để 30 FPS (mạng yếu: 20 FPS). Máy dưới 4 nhân chọn tối đa 60 FPS.": "Higher FPS looks smoother but works the phone harder and uses more data. For all-day game idling, use 30 FPS (weak network: 20 FPS). Phones with fewer than 4 cores go up to 60 FPS.",
"Hết lượt miễn phí vẫn quay tiếp được. Luôn hỏi lại trước khi trừ tiền.": "You can keep spinning after your free spins run out. Always asks before charging.",
"Hệ thống đang bảo trì. Vui lòng quay lại sau.": "The system is under maintenance. Please come back later.",
"Tải bản mới nhất mới dùng tiếp được. Tài khoản và máy của bạn giữ nguyên.": "Download the latest version to keep using the app. Your account and phones are kept.",
"Đã tạo đơn! Máy đang khởi tạo (khoảng 2–3 phút) — danh sách tự cập nhật khi máy chạy.": "Order created! The phone is being set up (about 2–3 minutes) — the list updates by itself when it's running.",
"• 💎 Blue chỉ dùng cho cloud phone (thuê / gia hạn), 1 💎 = 1đ. Không dùng cho sản phẩm khác.": "• 💎 Blue is for cloud phones only (rent / renew), 1 💎 = 1đ. Not for other products.",
"🎁 Chúc mừng! Bạn nhận được": "🎁 Congratulations! You got",
"🎉 Chúc mừng! Bạn nhận được": "🎉 Congratulations! You got",
"🎫 Bạn đã nhận mã của đợt này rồi.": "🎫 You've already got this round's code.",
"📜 Thể lệ  ▾": "📜 Rules  ▾",
"📱 Bạn đã dùng thử 1 máy rồi.": "📱 You've already used 1 trial phone.",
"🔒 Nạp tiền lần đầu để mở khoá trả bằng Blue. Blue vẫn được tích bình thường.": "🔒 Top up for the first time to unlock paying with Blue. You still earn Blue as usual."
}

TPL = [
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, dành cho tài khoản đã nạp từ {1} trong chương trình, tối đa {2} lượt mua + vé/ngày. Lượt mua chỉ trúng mã {3}; mã lớn hơn có ở lượt nạp tiền và vé may mắn. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, for accounts that have topped up from {1} during the event, up to {2} bought spins + tickets/day. Bought spins only win {3} codes; bigger codes come from top-up spins and lucky tickets. Always asks before charging."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, dành cho tài khoản đã nạp từ {1} trong chương trình, tối đa {2} lượt mua + vé/ngày. Lượt mua chỉ trúng mã {3}; mã lớn hơn có ở lượt nạp tiền. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, for accounts that have topped up from {1} during the event, up to {2} bought spins + tickets/day. Bought spins only win {3} codes; bigger codes come from top-up spins. Always asks before charging."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, dành cho tài khoản đã nạp từ {1} trong chương trình. Lượt mua chỉ trúng mã {2}; mã lớn hơn có ở lượt nạp tiền và vé may mắn. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, for accounts that have topped up from {1} during the event. Bought spins only win {2} codes; bigger codes come from top-up spins and lucky tickets. Always asks before charging."
],
[
"Tối đa {0}GB RAM · {1} nhân · mỗi tài khoản 1 máy · dành cho tài khoản đã nạp 1 lần từ {2}. Hết {3} (tính từ lúc máy chạy) máy và dữ liệu tự xoá, không gia hạn được — muốn dùng tiếp thì thuê máy.",
"Up to {0}GB RAM · {1} cores · 1 phone per account · for accounts that have topped up once from {2}. After {3} (from when the phone starts) the phone and its data are deleted and can't be renewed — rent a phone to keep going."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, dành cho tài khoản đã nạp từ {1} trong chương trình. Lượt mua chỉ trúng mã {2}; mã lớn hơn có ở lượt nạp tiền. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, for accounts that have topped up from {1} during the event. Bought spins only win {2} codes; bigger codes come from top-up spins. Always asks before charging."
],
[
"💳 Mỗi lệnh nạp thành công từ {0} trong thời gian chương trình: cứ {1} = {2} lượt quay (ví dụ nạp {3} = {4} lượt). Tính nạp ngân hàng và crypto; nạp qua Google Play không tính lượt.",
"💳 Every successful top-up from {0} during the event: each {1} = {2} spins (e.g. top up {3} = {4} spins). Bank and crypto top-ups count; Google Play top-ups don't earn spins."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, tối đa {1} lượt mua + vé/ngày. Lượt mua chỉ trúng mã {2}; mã lớn hơn có ở lượt nạp tiền và vé may mắn. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, up to {1} bought spins + tickets/day. Bought spins only win {2} codes; bigger codes come from top-up spins and lucky tickets. Always asks before charging."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, tối đa {1} lượt mua + vé/ngày. Lượt mua chỉ trúng mã {2}; mã lớn hơn có ở lượt nạp tiền. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, up to {1} bought spins + tickets/day. Bought spins only win {2} codes; bigger codes come from top-up spins. Always asks before charging."
],
[
"Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp đó), dùng 1 lần, hạn {0} ngày, giảm tối đa {1}. Chỉ dùng cho cloud phone: thuê, gia hạn, nâng cấp máy.",
"1 code per account (the highest tier of that top-up), single use, valid {0} days, up to {1} off. Cloud phones only: rent, renew, upgrade."
],
[
"Tối đa {0}GB RAM · {1} nhân · mỗi tài khoản 1 máy. Hết {2} (tính từ lúc máy chạy) máy và dữ liệu tự xoá, không gia hạn được — muốn dùng tiếp thì thuê máy.",
"Up to {0}GB RAM · {1} cores · 1 phone per account. After {2} (from when the phone starts) the phone and its data are deleted and can't be renewed — rent a phone to keep going."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, dành cho tài khoản đã nạp từ {1} trong chương trình, tối đa {2} lượt mua + vé/ngày. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, for accounts that have topped up from {1} during the event, up to {2} bought spins + tickets/day. Always asks before charging."
],
[
"Dành cho tài khoản đã nạp 1 lần từ {0}. Mỗi tài khoản 1 máy (tối đa {1}GB RAM · {2} nhân). Hết giờ, máy và dữ liệu tự xoá — muốn dùng tiếp thì thuê máy.",
"For accounts that have topped up once from {0}. 1 phone per account (up to {1}GB RAM · {2} cores). When time's up, the phone and its data are deleted — rent a phone to keep going."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư. Lượt mua chỉ trúng mã {1}; mã lớn hơn có ở lượt nạp tiền và vé may mắn. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance. Bought spins only win {1} codes; bigger codes come from top-up spins and lucky tickets. Always asks before charging."
],
[
"🍀 Vé may mắn: {0}/vé = 1 lượt quay riêng (không dùng lượt miễn phí), trừ vào số dư. Tỷ lệ công khai: {1}. Mã từ vé không giới hạn số lượng.",
"🍀 Lucky ticket: {0}/ticket = 1 separate spin (doesn't use free spins), charged to your balance. Public odds: {1}. Ticket codes are unlimited."
],
[
"Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp đó), dùng 1 lần, hạn {0} ngày. Chỉ dùng cho cloud phone: thuê, gia hạn, nâng cấp máy.",
"1 code per account (the highest tier of that top-up), single use, valid {0} days. Cloud phones only: rent, renew, upgrade."
],
[
"🎟 Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn {0} ngày, giữ dùng sau hoặc tặng bạn bè dùng đều được, giảm tối đa {1}.",
"🎟 Every spin wins a discount code: single use on 1 order, valid {0} days, keep it for later or gift it to a friend, up to {1} off."
],
[
"• 💎 Blue chỉ dùng cho cloud phone (thuê / gia hạn), 1 💎 = 1đ, dùng được khi tài khoản đã nạp từ {0}. Không dùng cho sản phẩm khác.",
"• 💎 Blue is for cloud phones only (rent / renew), 1 💎 = 1đ, usable once your account has topped up from {0}. Not for other products."
],
[
"Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp) · dùng 1 lần · hạn {0} ngày · chỉ cho cloud phone (thuê / gia hạn / nâng cấp).",
"1 code per account (the highest tier of that top-up) · single use · valid {0} days · cloud phones only (rent / renew / upgrade)."
],
[
"Mỗi tài khoản chỉ được thuê tối đa {0} máy — bạn đã có {1} máy.\nGia hạn máy đang có, hoặc xoá máy cũ (trên web) để thuê máy khác.",
"Each account can rent at most {0} phones — you already have {1}.\nRenew a phone you have, or delete an old one (on the website) to rent another."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư. Lượt mua chỉ trúng mã {1}; mã lớn hơn có ở lượt nạp tiền. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance. Bought spins only win {1} codes; bigger codes come from top-up spins. Always asks before charging."
],
[
"🎟 Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn {0} ngày, chỉ tài khoản quay trúng dùng được, giảm tối đa {1}.",
"🎟 Every spin wins a discount code: single use on 1 order, valid {0} days, only the winning account can use it, up to {1} off."
],
[
"Dùng 1 lần · hạn đến {0} · giữ dùng sau hoặc tặng bạn bè dùng đều được. Nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn máy.",
"Single use · valid until {0} · keep it for later or gift it to a friend. Enter it in the 🏷️ Discount code box when renting / renewing a phone."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, dành cho tài khoản đã nạp từ {1} trong chương trình. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, for accounts that have topped up from {1} during the event. Always asks before charging."
],
[
"🎟 Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn {0} ngày, giữ dùng sau hoặc tặng bạn bè dùng đều được.",
"🎟 Every spin wins a discount code: single use on 1 order, valid {0} days, keep it for later or gift it to a friend."
],
[
"Mỗi tài khoản 1 máy (tối đa {0}GB RAM · {1} nhân). Hết giờ, máy và dữ liệu tự xoá — muốn dùng tiếp thì thuê máy.",
"1 phone per account (up to {0}GB RAM · {1} cores). When time's up, the phone and its data are deleted — rent a phone to keep going."
],
[
"1 Blue = 1đ khi thuê / gia hạn điện thoại đám mây (tối đa {0}% mỗi đơn) — bật 💎 Trả bằng Blue lúc thanh toán.",
"1 Blue = 1đ when renting / renewing cloud phones (up to {0}% of each order) — turn on 💎 Pay with Blue at checkout."
],
[
"Máy chủ Android {0} chỉ còn trống {1}GB RAM và {2} nhân — chọn ít máy hơn, cấu hình nhỏ hơn hoặc bản Android khác.",
"The Android {0} server only has {1}GB RAM and {2} cores free — pick fewer phones, a smaller setup or another Android version."
],
[
"🎟 Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn {0} ngày, chỉ tài khoản quay trúng dùng được.",
"🎟 Every spin wins a discount code: single use on 1 order, valid {0} days, only the winning account can use it."
],
[
"Dùng 1 lần · hạn đến {0} · chỉ tài khoản của bạn dùng được. Nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn máy.",
"Single use · valid until {0} · only your account can use it. Enter it in the 🏷️ Discount code box when renting / renewing a phone."
],
[
". Hết {0} (tính từ lúc máy chạy) máy và dữ liệu tự xoá, không gia hạn được — muốn dùng tiếp thì thuê máy.",
". After {0} (from when the phone starts) the phone and its data are deleted and can't be renewed — rent a phone to keep going."
],
[
"Tích Blue để thuê / gia hạn máy rẻ hơn — 1 Blue = 1đ. Cách nhận:\n\n{0}\n\nMở Tích Blue để điểm danh ngay?",
"Earn Blue to rent / renew phones for less — 1 Blue = 1đ. How to earn:\n\n{0}\n\nOpen Earn Blue to check in now?"
],
[
"🎁 Bạn được tặng mã giảm giá cloud phone:  {0}  — mã nằm ở 🎁 Ưu đãi, bấm chọn khi thuê / gia hạn máy.",
"🎁 You got a cloud phone discount code:  {0}  — it's in 🎁 Deals; pick it when renting / renewing a phone."
],
[
"Không cần nạp đủ {0} — có số dư là mua được. Lượt mua trúng mã {1}. Luôn hỏi lại trước khi trừ tiền.",
"No need to top up {0} — any balance can buy one. Bought spins win {1} codes. Always asks before charging."
],
[
"Nâng “{0}” lên {1}GB RAM · {2} nhân, trừ khoảng {3} từ số dư? (mã {4})\nMáy sẽ tự khởi động lại khoảng 1 phút.",
"Upgrade “{0}” to {1}GB RAM · {2} cores, deducting about {3} from your balance? (mã {4})\nThe phone will restart for about 1 minute."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư, tối đa {1} lượt mua + vé/ngày. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance, up to {1} bought spins + tickets/day. Always asks before charging."
],
[
"Mỗi tài khoản dùng tối đa {0}mã giảm giá mỗi ngày — hôm nay bạn đã dùng đủ, mai dùng tiếp nhé.",
"Each account can use at most {0} discount codes a day — you've used them all today; use more tomorrow."
],
[
"Xoá toàn bộ dữ liệu của {0}?\n\nApp trở về như mới cài: acc đăng nhập, cài đặt trong app sẽ mất.",
"Clear all data of {0}?\n\nThe app goes back to freshly installed: signed-in accounts and in-app settings will be lost."
],
[
"{0}\n\nDùng Blue: bật \"💎 Trả bằng Blue\" khi thuê / gia hạn máy — 1 Blue = 1đ, tối đa {1}% mỗi đơn.",
"{0}\n\nUsing Blue: turn on \"💎 Pay with Blue\" when renting / renewing a phone — 1 Blue = 1đ, up to {1}% of each order."
],
[
"Hết lượt miễn phí vẫn quay tiếp được. Lượt mua trúng mã {0}. Luôn hỏi lại trước khi trừ tiền.",
"You can keep spinning after your free spins run out. Bought spins win {0} codes. Always asks before charging."
],
[
"Đã tạo đơn {0} máy! Máy đang khởi tạo (khoảng 2–3 phút) — danh sách tự cập nhật khi máy chạy.",
"Created order for {0} phones! The phone is being set up (about 2–3 minutes) — the list updates by itself when it's running."
],
[
"{0}\n\nDùng Blue: bật \"💎 Trả bằng Blue\" khi thuê / gia hạn máy — 1 Blue = 1đ, trả được cả đơn.",
"{0}\n\nUsing Blue: turn on \"💎 Pay with Blue\" when renting / renewing a phone — 1 Blue = 1đ, can pay a whole order."
],
[
"Nâng “{0}” lên {1}GB RAM · {2} nhân, trừ khoảng {3} từ số dư?\nMáy sẽ tự khởi động lại khoảng 1 phút.",
"Upgrade “{0}” to {1}GB RAM · {2} cores, deducting about {3} from your balance?\nThe phone will restart for about 1 minute."
],
[
"Thuê điện thoại Android đám mây chạy 24/7 ở CloudBlue — đăng ký qua link của mình nhé: {0}",
"Rent a 24/7 Android cloud phone at CloudBlue — sign up with my link: {0}"
],
[
"Android {0} tối đa {1}GB · {2} nhân → máy mới sẽ hạ còn {3}GB · {4} nhân, không hoàn tiền phần chênh.",
"Android {0} allows up to {1}GB · {2} cores → the new phone drops to {3}GB · {4} cores, with no refund for the difference."
],
[
"📱 Bạn được dùng thử 1 cloud phone {0} miễn phí — mở + Thuê máy, tích “Dùng thử MIỄN PHÍ”.",
"📱 You can try 1 cloud phone {0} free — open + Rent a phone and tick “FREE trial”."
],
[
"Bạn được dùng thử 1 cloud phone {0} miễn phí — mở + Thuê máy, tích “Dùng thử MIỄN PHÍ”.",
"You can try 1 cloud phone {0} free — open + Rent a phone and tick “FREE trial”."
],
[
"Huỷ máy “{0}”?\n\nMáy và TOÀN BỘ dữ liệu trong máy sẽ bị XOÁ vĩnh viễn, không hoàn tiền.",
"Cancel the phone “{0}”?\n\nThe phone and ALL its data will be PERMANENTLY DELETED, with no refund."
],
[
"Đơn giá {0} / ngày (CTV −{1}%)  ·  Hạn mới: {2}\nThanh toán: {3} (🏷️ −{4}) (💎 −{5} Blue)   ·   Số dư: {6}",
"Price {0} / day (CTV −{1}%)  ·  New expiry: {2}\nPayment: {3} (🏷️ −{4}) (💎 −{5} Blue)   ·   Balance: {6}"
],
[
"Cấu hình mới: {0}GB RAM · {1} nhân\nTrả thêm cho thời gian còn lại: {2} (🏷️ −{3})   ·   Số dư: {4}",
"New setup: {0}GB RAM · {1} cores\nExtra for the remaining time: {2} (🏷️ −{3})   ·   Balance: {4}"
],
[
"🎁 Nhận máy tặng thành công — máy đang được tạo (Android {0} · {1}GB · {2} nhân · {3} ngày).",
"🎁 Gift phone redeemed — the phone is being created (Android {0} · {1}GB · {2} cores · {3} days)."
],
[
"Chưa khởi động lại được: {0} Bấm R để thử lại; vẫn lỗi thì báo hỗ trợ kèm tên máy.",
"Couldn't restart yet: {0} Press R to try again; if it still fails, contact support with the phone's name."
],
[
"Máy chủ chỉ còn trống {0}GB RAM và {1} nhân — chọn ít máy hơn hoặc cấu hình nhỏ hơn.",
"The server only has {0}GB RAM and {1} cores free — pick fewer phones or a smaller setup."
],
[
"• Mỗi đơn trả bằng tiền (thuê, gia hạn, nâng cấp, mua hàng): hoàn {0}% bằng Blue",
"• Every order paid with money (rent, renew, upgrade, shop): {0}% back in Blue"
],
[
"Khởi động lại máy “{0}”?\n\nMáy tắt khoảng 1 phút rồi tự bật lại. Dữ liệu vẫn giữ.",
"Restart the phone “{0}”?\n\nThe phone turns off for about 1 minute and comes back by itself. Your data is kept."
],
[
"Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp đó), dùng 1 lần, hạn {0} ngày",
"1 code per account (the highest tier of that top-up), single use, valid {0} days"
],
[
"Đơn giá {0} / ngày (CTV −{1}%)  ·  Hạn mới: {2}\nThanh toán: {3} (💎 −{4} Blue)   ·   Số dư: {5}",
"Price {0} / day (CTV −{1}%)  ·  New expiry: {2}\nPayment: {3} (💎 −{4} Blue)   ·   Balance: {5}"
],
[
"• Bạn bè bạn mời nạp tiền lần đầu từ {0} (khác mạng / thiết bị): +{1} Blue mỗi bạn",
"• A friend you invited tops up for the first time from {0} (different network / device): +{1} Blue per friend"
],
[
"Cấu hình mới: {0}GB RAM · {1} nhân\nTrả thêm cho thời gian còn lại: {2}   ·   Số dư: {3}",
"New setup: {0}GB RAM · {1} cores\nExtra for the remaining time: {2}   ·   Balance: {3}"
],
[
"✓ {0} App / game hỗ trợ ngang sẽ hiện ngang; app chỉ chạy màn dọc thì vẫn dọc.",
"✓ {0} Apps / games that support landscape show in landscape; portrait-only apps stay portrait."
],
[
"🎯 Lượt mua chỉ trúng mã {0} — mã lớn hơn có ở lượt nạp tiền và 🍀 vé may mắn.\n\n",
"🎯 Bought spins only win {0} codes — bigger codes come from top-up spins and 🍀 lucky tickets.\n\n"
],
[
"Có bản app mới {0} — bấm vào đây để cập nhật (app tự tải, máy này tự mở lại).",
"New app version {0} — click here to update (the app downloads it and reopens this phone)."
],
[
"Giải của vé (tỷ lệ công khai):\n{0}\n\nTrừ {1} vào số dư · còn lại {2}.{3}\n\nTrả {4} và quay?",
"Ticket prizes (public odds):\n{0}\n\nDeducts {1} from your balance · {2} left.{3}\n\nPay {4} and spin?"
],
[
"🔄 Máy mới đổi sang Android {0} — đang tạo (2–5 phút), xong thì máy cũ tự xoá.",
"🔄 Switching to Android {0} — the new phone is being created (2–5 minutes); the old one is deleted when it's done."
],
[
"Cập nhật lên bản {0} mới dùng tiếp được. Tài khoản và máy của bạn giữ nguyên.",
"Update to version {0} to keep using the app. Your account and phones are kept."
],
[
"Không cần nạp đủ {0} — có số dư là mua được. Luôn hỏi lại trước khi trừ tiền.",
"No need to top up {0} — any balance can buy one. Always asks before charging."
],
[
"Đơn giá {0} / ngày  ·  Hạn mới: {1}\nThanh toán: {2} (🏷️ −{3}) (💎 −{4} Blue)   ·   Số dư: {5}",
"Price {0} / day  ·  New expiry: {1}\nPayment: {2} (🏷️ −{3}) (💎 −{4} Blue)   ·   Balance: {5}"
],
[
"Nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn máy. Mã dùng 1 lần, hạn {0} ngày.",
"Enter it in the 🏷️ Discount code box when renting / renewing a phone. Single use, valid {0} days."
],
[
"🎁 Máy dùng thử {0} giờ — hết giờ máy và dữ liệu tự xoá, không gia hạn được.",
"🎁 {0}-hour trial phone — when time's up, the phone and its data are deleted; it can't be renewed."
],
[
"{0}. Vòng đổi sang mặt vé riêng, trừ vào số dư, luôn hỏi lại trước khi trừ.",
"{0}. The wheel switches to its own ticket face, charged to your balance, always asking before charging."
],
[
"Đơn giá {0} / ngày (CTV −{1}%)  ·  Hạn mới: {2}\nThanh toán: {3} (🏷️ −{4})   ·   Số dư: {5}",
"Price {0} / day (CTV −{1}%)  ·  New expiry: {2}\nPayment: {3} (🏷️ −{4})   ·   Balance: {5}"
],
[
"• Bạn bè bạn mời nạp tiền lần đầu (khác mạng / thiết bị): +{0} Blue mỗi bạn",
"• A friend you invited tops up for the first time (different network / device): +{0} Blue per friend"
],
[
"🔒 Nạp tiền từ {0} để mở khoá trả bằng Blue. Blue vẫn được tích bình thường.",
"🔒 Top up from {0} to unlock paying with Blue. You still earn Blue as usual."
],
[
"Bỏ tất cả bản clone của {0}?\n\nAcc đăng nhập trong các bản clone sẽ bị xoá.",
"Remove all clones of {0}?\n\nAccounts signed in on the clones will be deleted."
],
[
"🎟 Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn {0} ngày, ",
"🎟 Every spin wins a discount code: single use on 1 order, valid {0} days, "
],
[
" Lượt mua chỉ trúng mã {0}; mã lớn hơn có ở lượt nạp tiền và vé may mắn.",
" Bought spins only win {0} codes; bigger codes come from top-up spins and lucky tickets."
],
[
"Cứ {0} nạp được {1} lượt quay miễn phí. Nạp ngân hàng hay crypto đều tính.",
"Every {0} you top up earns {1} free spins. Bank and crypto top-ups both count."
],
[
"Quay thêm 1 lượt giá {0} — số dư của bạn còn {1}.\n\nNạp thêm để quay tiếp?",
"One extra spin costs {0} — your balance is {1}.\n\nTop up to keep spinning?"
],
[
"Đã nâng lên {0}GB · {1} nhân — máy nhận cấu hình mới trong khoảng 1 phút.",
"Upgraded to {0}GB · {1} cores — the phone gets the new setup in about 1 minute."
],
[
"Đơn giá {0} / ngày  ·  Hạn mới: {1}\nThanh toán: {2} (💎 −{3} Blue)   ·   Số dư: {4}",
"Price {0} / day  ·  New expiry: {1}\nPayment: {2} (💎 −{3} Blue)   ·   Balance: {4}"
],
[
"🎡 Vòng quay bắt đầu {0} — lệnh nạp từ lúc đó mới được tính lượt quay.",
"🎡 The wheel starts {0} — only top-ups from then on earn spins."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư. Luôn hỏi lại trước khi trừ tiền.",
"➕ Buy spins: {0}/spin, charged to your balance. Always asks before charging."
],
[
"Làm video về CloudBlue: {0} view = {1} 💎 Blue. View tăng thì nhận thêm.",
"Make videos about CloudBlue: {0} views = {1} 💎 Blue. More views, more Blue."
],
[
"Đơn giá {0} / ngày (CTV −{1}%)  ·  Hạn mới: {2}\nThanh toán: {3}   ·   Số dư: {4}",
"Price {0} / day (CTV −{1}%)  ·  New expiry: {2}\nPayment: {3}   ·   Balance: {4}"
],
[
"\n\nMáy dùng thử {0} — không trừ tiền. Hết giờ máy và dữ liệu tự xoá.",
"\n\nTrial phone {0} — free of charge. When time's up, the phone and its data are deleted."
],
[
"\n🔒 Nạp tiền từ {0} để mở khoá trả bằng Blue (vẫn tích bình thường).",
"\n🔒 Top up from {0} to unlock paying with Blue (you still earn it as usual)."
],
[
"Gỡ {0} khỏi máy?\n\nDữ liệu của app sẽ bị xoá, {1} bản clone cũng bị gỡ.",
"Uninstall {0} from the phone?\n\nThe app's data will be deleted, and its {1} clones will be uninstalled too."
],
[
"Thư mục cập nhật lần trước còn bị giữ ({0}) — thử lại sau ít phút.",
"The previous update's folder is still in use ({0}) — try again in a few minutes."
],
[
"Không giải nén được bản mới (ổ đĩa đầy / không có quyền ghi?): {0}",
"Couldn't unpack the new version (disk full / no write permission?): {0}"
],
[
"Đơn giá {0} / ngày  ·  Hạn mới: {1}\nThanh toán: {2} (🏷️ −{3})   ·   Số dư: {4}",
"Price {0} / day  ·  New expiry: {1}\nPayment: {2} (🏷️ −{3})   ·   Balance: {4}"
],
[
"Cập nhật lỗi và chưa trả lại được bản cũ — app cũ đang nằm ở: {0}",
"The update failed and the old version couldn't be restored — the old app is at: {0}"
],
[
"🎟 Mỗi tài khoản dùng tối đa {0} mã giảm giá mỗi ngày.  Hôm nay: {1}/{2}",
"🎟 Each account can use at most {0} discount codes a day.  Today: {1}/{2}"
],
[
"Cấu hình mới: {0}GB RAM · {1} nhân\nTrả thêm cho thời gian còn lại: {2}",
"New setup: {0}GB RAM · {1} cores\nExtra for the remaining time: {2}"
],
[
"Vé may mắn giá {0} — số dư của bạn còn {1}.\n\nNạp thêm để dùng vé?",
"A lucky ticket costs {0} — your balance is {1}.\n\nTop up to use a ticket?"
],
[
"🔄 Đang xoá máy cũ… xoá xong tự tạo máy Android {0} (2–5 phút).",
"🔄 Deleting the old phone… then creating the Android {0} phone (2–5 minutes)."
],
[
"🎯 Lượt mua chỉ trúng mã {0} — mã lớn hơn có ở lượt nạp tiền.\n\n",
"🎯 Bought spins only win {0} codes — bigger codes come from top-up spins.\n\n"
],
[
"Bạn đang có {0} lượt quay — lượt nào cũng trúng 1 mã giảm giá",
"You have {0} spins — every spin wins a discount code"
],
[
"📅 Điểm danh mỗi ngày: +{0} Blue (đủ {1} ngày liền thưởng thêm +{2})",
"📅 Daily check-in: +{0} Blue ({1} days in a row earns an extra +{2})"
],
[
"✓ Đã nhận {0} — số dư đã được cộng.   🎡 +{1} lượt quay may mắn!",
"✓ Received {0} — your balance has been topped up.   🎡 +{1} lucky spins!"
],
[
"Đang xoá máy cũ… xoá xong tự tạo máy Android {0} (2–5 phút).",
"Deleting the old phone… then creating the Android {0} phone (2–5 minutes)."
],
[
"🎯 Lượt mua chỉ trúng mã {0} — mã lớn hơn có ở lượt nạp tiền",
"🎯 Bought spins only win {0} codes — bigger codes come from top-up spins"
],
[
"Có thư mục lạ trùng tên {0} — đổi tên / xoá nó rồi thử lại.",
"There's an unknown folder with the same name {0} — rename / delete it and try again."
],
[
"Đơn giá {0} / ngày  ·  Hạn mới: {1}\nThanh toán: {2}   ·   Số dư: {3}",
"Price {0} / day  ·  New expiry: {1}\nPayment: {2}   ·   Balance: {3}"
],
[
"Nạp {0} = {1} lượt · lượt nào cũng trúng mã giảm giá · số dư {2}",
"Top up {0} = {1} spins · every spin wins a discount code · balance {2}"
],
[
" Lượt mua chỉ trúng mã {0}; mã lớn hơn có ở lượt nạp tiền.",
" Bought spins only win {0} codes; bigger codes come from top-up spins."
],
[
"🆕 Tài khoản mới — sau {0} giờ mới bắt đầu tích Blue được.",
"🆕 New account — you can start earning Blue after {0} hours."
],
[
"Dùng thử miễn phí dành cho tài khoản đã nạp 1 lần từ {0}.",
"Free trial is for accounts that have topped up once from {0}."
],
[
" Lượt mua chỉ trúng mã {0}; mã lớn hơn có ở lượt nạp tiền",
" Bought spins only win {0} codes; bigger codes come from top-up spins"
],
[
"🔄 Máy cũ đã xoá — đang tạo máy Android {0} (2–5 phút).\n{1}",
"🔄 Old phone deleted — creating the Android {0} phone (2–5 minutes).\n{1}"
],
[
"🔄 Máy cũ đã xoá — đang tạo máy Android {0} (2–5 phút).",
"🔄 Old phone deleted — creating the Android {0} phone (2–5 minutes)."
],
[
"📱 Nạp 1 lần từ {0} → dùng thử 1 cloud phone {1} miễn phí.",
"📱 Top up once from {0} → try 1 cloud phone {1} free."
],
[
"🎟 Mỗi tài khoản dùng tối đa {0} mã giảm giá mỗi ngày.",
"🎟 Each account can use at most {0} discount codes a day."
],
[
"Gói {0} chạy trên Android {1} — đã chuyển sang Android {2}.",
"The {0} plan runs on Android {1} — switched to Android {2}."
],
[
", dành cho tài khoản đã nạp từ {0} trong chương trình",
", for accounts that have topped up from {0} during the event"
],
[
"{0}   ·   Android {1} · {2} nhân · {3}GB · {4} FPS · {5} ngày × {6} máy",
"{0}   ·   Android {1} · {2} cores · {3}GB · {4} FPS · {5} days × {6} phones"
],
[
"Bấm phím U hoặc bấm vào đây để cập nhật lên bản {0}.",
"Press U or click here to update to version {0}."
],
[
"2. Đăng công khai lên {0}. Nói hoặc ghi rõ tên web {1}.",
"2. Post it publicly on {0}. Say or show the website name {1}."
],
[
"Tối đa {0}GB RAM · {1} nhân — để mặc định là dùng được.",
"Up to {0}GB RAM · {1} cores — the defaults work fine."
],
[
"Nạp 1 lần từ {0} → dùng thử 1 cloud phone {1} miễn phí.",
"Top up once from {0} → try 1 cloud phone {1} free."
],
[
"Nâng “{0}” lên {1}GB RAM · {2} nhân, trừ khoảng {3} từ số dư?",
"Upgrade “{0}” to {1}GB RAM · {2} cores, deducting about {3} from your balance?"
],
[
"Đã chép: {0}   ·   ⏳ vẫn đang chờ ngân hàng báo có…",
"Copied: {0}   ·   ⏳ still waiting for the bank to confirm…"
],
[
"Hôm nay đã nhận {0} / {1} Blue (điểm danh + nhiệm vụ)",
"Today you've got {0} / {1} Blue (check-in + missions)"
],
[
"Hệ thống đang bảo trì: {0}. Vui lòng quay lại sau.",
"The system is under maintenance: {0}. Please come back later."
],
[
"Đã duyệt {0} view  ·  đã nhận {1} 💎  ·  bạn báo {2} view",
"Approved {0} views  ·  received {1} 💎  ·  you reported {2} views"
],
[
"⏰ Thời gian: từ {0} đến khi có thông báo kết thúc.",
"⏰ When: from {0} until an end is announced."
],
[
"Đã nhận {0} 💎   ·   tháng này {1} 💎   ·   chờ duyệt {2}",
"Received {0} 💎   ·   this month {1} 💎   ·   pending {2}"
],
[
"Tài khoản của bạn chỉ còn được thuê thêm {0} máy.",
"Your account can only rent {0} more phones."
],
[
"Máy chủ Android {0} đang bảo trì — chọn bản khác.",
"The Android {0} server is under maintenance — pick another version."
],
[
"Tải bản mới lỗi (HTTP {0}) — thử lại sau ít phút.",
"Downloading the new version failed (HTTP {0}) — try again in a few minutes."
],
[
"Chép bản mới bị lỗi ({0}) — đã giữ nguyên bản cũ.",
"Copying the new version failed ({0}) — kept the old version."
],
[
"Hôm nay bạn chưa điểm danh — nhận +{0} Blue ngay?",
"You haven't checked in today — get +{0} Blue now?"
],
[
"Android {0} · {1} máy · {2}GB · {3} nhân · {4} ngày · {5} · {6} FPS",
"Android {0} · {1} phones · {2}GB · {3} cores · {4} days · {5} · {6} FPS"
],
[
"🎁 Lần nạp này được tặng mã giảm {0}% cloud phone",
"🎁 This top-up earns a {0}% cloud phone discount code"
],
[
"Đã đổi sang {0} FPS — mở lại cửa sổ máy là thấy.",
"Switched to {0} FPS — reopen the phone window to see it."
],
[
"{0}\n\nXem lại bất cứ lúc nào: bấm nút 💎 trên app.",
"{0}\n\nCheck it any time: click the 💎 button in the app."
],
[
"Nạp {0} = {1} lượt quay · mua lượt {2} · 🍀 vé may mắn {3}",
"Top up {0} = {1} spins · buy a spin {2} · 🍀 lucky ticket {3}"
],
[
"🎁 Bạn được mời nạp tiền lần đầu (từ {0}): +{1} Blue",
"🎁 A friend you invited tops up for the first time (from {0}): +{1} Blue"
],
[
"Đã lưu ảnh vào {0} — bấm vào đây để mở thư mục.",
"Saved the screenshot to {0} — click here to open the folder."
],
[
"⚙️ Tự chỉnh cấu hình    {0}GB · {1} nhân · {2} · {3} FPS",
"⚙️ Custom setup    {0}GB · {1} cores · {2} · {3} FPS"
],
[
"Tối đa {0}GB RAM · {1} nhân · mỗi tài khoản 1 máy",
"Up to {0}GB RAM · {1} cores · 1 phone per account"
],
[
"{0}   ·   Android {1} · {2} nhân · {3}GB · {4} FPS · {5} ngày",
"{0}   ·   Android {1} · {2} cores · {3}GB · {4} FPS · {5} days"
],
[
"💸 Mỗi đơn trả bằng tiền: hoàn {0}% thành Blue",
"💸 Every order paid with money: {0}% back as Blue"
],
[
"Dùng thử miễn phí {0} · Android {1} · {2}GB · {3} nhân",
"Free trial {0} · Android {1} · {2}GB · {3} cores"
],
[
"Không mở được cửa sổ máy. Chi tiết trong:\n{0}",
"Couldn't open the phone window. Details in:\n{0}"
],
[
"Đang dùng: {0} dp   ·   mặc định của máy: {1} dp",
"In use: {0} dp   ·   phone default: {1} dp"
],
[
"📱 Mở dùng thử 1 cloud phone {0} giờ miễn phí",
"📱 Unlocks a free {0}-hour cloud phone trial"
],
[
"{0}Trừ {1} vào số dư · còn lại {2}.{3}\n\nTrả {4} và quay?",
"{0}Deducts {1} from your balance · {2} left.{3}\n\nPay {4} and spin?"
],
[
"Không cần nạp đủ {0} — có số dư là mua được.",
"No need to top up {0} — any balance can buy one."
],
[
"Không ghi được file tải về (ổ đĩa đầy?): {0}",
"Couldn't write the downloaded file (disk full?): {0}"
],
[
"({0}GB × {1} + {2} nhân × {3}) × {4} ngày − {5}% CTV × {6} máy",
"({0}GB × {1} + {2} cores × {3}) × {4} days − {5}% CTV × {6} phones"
],
[
"Gỡ {0} khỏi máy?\n\nDữ liệu của app sẽ bị xoá.",
"Uninstall {0} from the phone?\n\nThe app's data will be deleted."
],
[
"📱 Đã mở dùng thử 1 cloud phone {0}miễn phí.",
"📱 Unlocked a free {0}cloud phone trial."
],
[
"🔒 Nạp 1 lần từ {0} để mở dùng thử miễn phí.",
"🔒 Top up once from {0} to unlock the free trial."
],
[
"Máy mới: Android {0} · {1}GB · {2} nhân · {3} · {4} FPS",
"New phone: Android {0} · {1}GB · {2} cores · {3} · {4} FPS"
],
[
"Gỡ {0} khỏi máy?\n\nDữ liệu của app sẽ bị xoá",
"Uninstall {0} from the phone?\n\nThe app's data will be deleted"
],
[
"Đang tạo {0} bản clone {1} (mỗi bản ~20 giây)…",
"Creating {0} clones of {1} (~20 seconds each)…"
],
[
"Khởi động lại máy “{0}”? Mất khoảng 1 phút.",
"Restart the phone “{0}”? It takes about 1 minute."
],
[
"{0} Sửa hoặc xoá mã giảm giá để thanh toán.",
"{0} Edit or remove the discount code to pay."
],
[
" (khác mạng / thiết bị): +{0} Blue mỗi bạn",
" (different network / device): +{0} Blue per friend"
],
[
"🎡 Lệnh nạp này được +{0} lượt quay may mắn",
"🎡 This top-up earns +{0} lucky spins"
],
[
"🎁 Bạn được mời nạp tiền lần đầu: +{0} Blue",
"🎁 A friend you invited tops up for the first time: +{0} Blue"
],
[
"✓ Đã thêm máy “{0}” được chia sẻ cho bạn.",
"✓ Added the phone “{0}” shared with you."
],
[
" · dành cho tài khoản đã nạp 1 lần từ {0}",
" · for accounts that have topped up once from {0}"
],
[
"{0}   ·   Android {1} · {2} nhân · {3}GB · {4} FPS · ",
"{0}   ·   Android {1} · {2} cores · {3}GB · {4} FPS · "
],
[
"Android {0} · {1}GB · {2} nhân · đang dùng {3} FPS",
"Android {0} · {1}GB · {2} cores · using {3} FPS"
],
[
"Cập nhật lên bản {0} mới dùng tiếp được. ",
"Update to version {0} to keep using the app. "
],
[
"Android {0} · {1} máy · {2}GB · {3} nhân · {4} · {5} FPS",
"Android {0} · {1} phones · {2}GB · {3} cores · {4} · {5} FPS"
],
[
"{0}   ·   Android {1} · {2} nhân · {3}GB · {4} FPS · {5}",
"{0}   ·   Android {1} · {2} cores · {3}GB · {4} FPS · {5}"
],
[
"{0} khung/s · {1} Mbps · trễ mạng {2} ms · {3} · {4}",
"{0} fps · {1} Mbps · latency {2} ms · {3} · {4}"
],
[
"Dành cho tài khoản đã nạp 1 lần từ {0}. ",
"For accounts that have topped up once from {0}. "
],
[
"Chỉ còn {0} máy — chọn số lượng nhỏ hơn.",
"Only {0} phones left — pick a smaller quantity."
],
[
"Gia hạn “{0}” thêm {1} ngày, trừ {2} từ số dư?",
"Renew “{0}” for {1} more days, deducting {2} from your balance?"
],
[
"Gia hạn “{0}” thêm {1} ngày, trừ {2} từ số dư?{3}",
"Renew “{0}” for {1} more days, deducting {2} from your balance?{3}"
],
[
", dùng được khi tài khoản đã nạp từ {0}",
", usable once your account has topped up from {0}"
],
[
"🎡 Nạp từ {0} để được {1} lượt quay may mắn",
"🎡 Top up from {0} to get {1} lucky spins"
],
[
"Số bản clone muốn có (tổng, tối đa {0})",
"Number of clones you want (total, up to {0})"
],
[
"Mã chỉ dùng cho đơn từ {0} (đơn này {1}).",
"This code only works on orders from {0} (this order is {1})."
],
[
"{0}GB RAM · {1} nhân · {2} · {3} FPS · Android {4}",
"{0}GB RAM · {1} cores · {2} · {3} FPS · Android {4}"
],
[
"💎 +{0} Blue — nhiệm vụ mở máy hôm nay",
"💎 +{0} Blue — today's open-a-phone mission"
],
[
"Đang dùng Android {0} · {1}GB · {2} nhân · {3}",
"Using Android {0} · {1}GB · {2} cores · {3}"
],
[
"({0}GB × {1} + {2} nhân × {3}) × {4} ngày − {5}% CTV",
"({0}GB × {1} + {2} cores × {3}) × {4} days − {5}% CTV"
],
[
"Android {0}: hết chỗ cho cấu hình này",
"Android {0}: no room for this setup"
],
[
"Vòng quay may mắn · mã giảm đến {0}%",
"Lucky wheel · codes up to {0}% off"
],
[
"\nHôm nay còn mua được {0} lượt / vé.",
"\nYou can still buy {0} spins / tickets today."
],
[
"Đang tải lên {0}%  ({1} / {2} MB · {3} MB/s)…",
"Uploading {0}%  ({1} / {2} MB · {3} MB/s)…"
],
[
"({0}GB × {1} + {2} nhân × {3}) × {4} ngày × {5} máy",
"({0}GB × {1} + {2} cores × {3}) × {4} days × {5} phones"
],
[
"Nạp {0} = {1} lượt quay · 🍀 vé may mắn {2}",
"Top up {0} = {1} spins · 🍀 lucky ticket {2}"
],
[
"📱 Dùng thử cloud phone {0} miễn phí",
"📱 Free {0} cloud phone trial"
],
[
"✓ Đã nhận {0} — số dư đã được cộng.",
"✓ Received {0} — your balance has been topped up."
],
[
"➕ Mua lượt: {0}/lượt, trừ vào số dư",
"➕ Buy spins: {0}/spin, charged to your balance"
],
[
"⛔ Bắt buộc cập nhật — bản {0} đã cũ",
"⛔ Update required — version {0} is outdated"
],
[
"Số dư hiện tại: {0}   ·   Cần thêm {1}",
"Current balance: {0}   ·   Need {1} more"
],
[
"Android {0} · {1} máy · {2}GB · {3} nhân · ",
"Android {0} · {1} phones · {2}GB · {3} cores · "
],
[
"⏳ Đang nâng cấp lên {0}GB · {1} nhân…",
"⏳ Upgrading to {0}GB · {1} cores…"
],
[
"Số dư không đủ — cần nạp thêm {0}.",
"Not enough balance — top up {0}."
],
[
" (đủ {0} ngày liền thưởng thêm +{1})",
" ({0} days in a row earns an extra +{1})"
],
[
"Android {0}: máy chủ đang bảo trì",
"Android {0}: server under maintenance"
],
[
"Bản mới {0}  ·  {1} MB  (đang dùng {2})",
"New version {0}  ·  {1} MB  (using {2})"
],
[
"Đã duyệt {0} view  ·  đã nhận {1} 💎",
"Approved {0} views  ·  received {1} 💎"
],
[
"Đang tải bản mới… {0}%  ({1} / {2} MB)",
"Downloading the new version… {0}%  ({1} / {2} MB)"
],
[
"Nạp {0} = {1} lượt quay · mua lượt {2}",
"Top up {0} = {1} spins · buy a spin {2}"
],
[
"📅 Điểm danh mỗi ngày: +{0} Blue",
"📅 Daily check-in: +{0} Blue"
],
[
"Android {0}: CPU từ {1} đến {2} nhân.",
"Android {0}: CPU from {1} to {2} cores."
],
[
"{0}GB RAM · {1} nhân · Android {2} · {3}",
"{0}GB RAM · {1} cores · Android {2} · {3}"
],
[
"Bắt đầu {0} · nạp {1} = {2} lượt quay",
"Starts {0} · top up {1} = {2} spins"
],
[
"Bắt đầu {0}. Nạp {1} = {2} lượt quay.",
"Starts {0}. Top up {1} = {2} spins."
],
[
", tối đa {0} lượt mua + vé/ngày",
", up to {0} bought spins + tickets/day"
],
[
"   ·   mặc định của máy: {0} dp",
"   ·   phone default: {0} dp"
],
[
"Đang bật · {0} app được dùng su",
"On · {0} apps can use su"
],
[
"Có bản app mới {0} (đang dùng {1})",
"New app version {0} (using {1})"
],
[
"{0}% (mặc định)  ·  đang dùng {1}%",
"{0}% (default)  ·  in use {1}%"
],
[
"Nạp 1 lần từ {0}  →  mã giảm {1}%",
"Top up once from {0}  →  {1}% off code"
],
[
"Máy miễn phí tối đa {0}GB RAM.",
"Free phones get at most {0}GB RAM."
],
[
"  ·  Hạn mới: {0}\nThanh toán: {1}",
"  ·  New expiry: {0}\nPayment: {1}"
],
[
"Trừ {0} Blue (= {1}) · còn {2} Blue",
"Uses {0} Blue (= {1}) · {2} Blue left"
],
[
"Bạn có {0} Blue · 1 Blue = 1đ",
"You have {0} Blue · 1 Blue = 1đ"
],
[
"🎉 +{0} Blue — đủ chuỗi {1} ngày!",
"🎉 +{0} Blue — {1}-day streak complete!"
],
[
"💎 +{0} Blue — điểm danh ngày {1}",
"💎 +{0} Blue — check-in day {1}"
],
[
"Máy miễn phí tối đa {0} nhân.",
"Free phones get at most {0} cores."
],
[
"Android {0}: RAM từ {1} đến {2} GB.",
"Android {0}: RAM from {1} to {2} GB."
],
[
"({0}GB × {1} + {2} nhân × {3}) × {4} ngày",
"({0}GB × {1} + {2} cores × {3}) × {4} days"
],
[
"Hiện tại {0}GB RAM · {1} nhân · {2}",
"Now {0}GB RAM · {1} cores · {2}"
],
[
"✗ Chưa xoá dữ liệu được {0}: {1}",
"✗ Couldn't clear data of {0}: {1}"
],
[
"Không chụp được màn hình: {0}",
"Couldn't take a screenshot: {0}"
],
[
"{0}% trúng mã {1} · còn lại mã {2}%",
"{0}% chance of a {1} code · otherwise a {2}% code"
],
[
"💳 Nạp {0} để nhận {1} lượt quay",
"💳 Top up {0} to get {1} spins"
],
[
"Chưa khởi động lại được: {0}",
"Couldn't restart yet: {0}"
],
[
"còn {0} giờ {1} phút · hết hạn {2}",
"{0} h {1} min left · expires {2}"
],
[
"còn {0} ngày {1} giờ · hết hạn {2}",
"{0} d {1} h left · expires {2}"
],
[
"gửi tối đa {0} video / ngày",
"send up to {0} videos / day"
],
[
"🎉 Máy “{0}” giờ là của bạn!",
"🎉 The phone “{0}” is yours now!"
],
[
"    {0}GB · {1} nhân · {2} · {3} FPS",
"    {0}GB · {1} cores · {2} · {3} FPS"
],
[
"Dùng 1 lần · hạn đến {0} · ",
"Single use · valid until {0} · "
],
[
", {0} bản clone cũng bị gỡ.",
", and its {0} clones will be uninstalled too."
],
[
"{0} · {1} · 🤝 tặng bạn bè được",
"{0} · {1} · 🤝 can be gifted to friends"
],
[
"🎡 Quay ngay · còn {0} lượt",
"🎡 Spin now · {0} spins left"
],
[
"🎡 Quay tiếp · còn {0} lượt",
"🎡 Spin again · {0} spins left"
],
[
"App shop thêm sẵn · {0} MB",
"Shop's app · {0} MB"
],
[
"✓ Đã cập nhật lên bản {0}.",
"✓ Updated to version {0}."
],
[
"  ★ Dùng thử MIỄN PHÍ {0}",
"  ★ FREE trial {0}"
],
[
"Số ngày phải từ {0} đến {1}.",
"Days must be from {0} to {1}."
],
[
"Kiếm tiền · {0} view = {1} 💎",
"Earn money · {0} views = {1} 💎"
],
[
"Bản mới {0}  (đang dùng {1})",
"New version {0}  (using {1})"
],
[
"Số tiền tối thiểu là {0}.",
"The minimum amount is {0}."
],
[
"⏰ Thời gian: từ {0} đến {1}.",
"⏰ When: from {0} to {1}."
],
[
"{0} nhân · {1}GB RAM · {2} FPS",
"{0} cores · {1}GB RAM · {2} FPS"
],
[
"Trả về mặc định ({0} dp)",
"Reset to default ({0} dp)"
],
[
"Đang tải bản mới… {0} MB",
"Downloading the new version… {0} MB"
],
[
"Nạp từ {0} nhận mã đến {1}%",
"Top up from {0}, get codes up to {1}% off"
],
[
"✗ Không mở được kho: {0}",
"✗ Couldn't open the app store: {0}"
],
[
"Tạo mã chuyển khoản {0}",
"Create transfer code {0}"
],
[
"🎡 Quay ngay · +{0} lượt",
"🎡 Spin now · +{0} spins"
],
[
" Lượt mua trúng mã {0}.",
" Bought spins win {0} codes."
],
[
"Đã trừ {0} · số dư còn {1}",
"Charged {0} · balance {1}"
],
[
"Đổi FPS (đang {0} FPS)…",
"Change FPS (now {0} FPS)…"
],
[
", tối đa {0}% mỗi đơn.",
", up to {0}% of each order."
],
[
" (tối đa {0}% mỗi đơn)",
" (up to {0}% of each order)"
],
[
"➕ Quay thêm · {0}/lượt",
"➕ Extra spin · {0}/spin"
],
[
"{0} đang có {1} bản clone",
"{0} has {1} clones"
],
[
"Đang mở bản clone {0}…",
"Opening clone {0}…"
],
[
"✗ Chưa dừng được {0}: {1}",
"✗ Couldn't stop {0}: {1}"
],
[
"  ·  bạn báo {0} view",
"  ·  you reported {0} views"
],
[
"FPS phải từ {0} đến {1}.",
"FPS must be from {0} to {1}."
],
[
"Đã gia hạn +{0} ngày.",
"Renewed +{0} days."
],
[
"➕ Mua lượt quay · {0}",
"➕ Buy a spin · {0}"
],
[
"dùng thử {0} miễn phí",
"{0} free trial"
],
[
"Đang xoá dữ liệu {0}…",
"Clearing data of {0}…"
],
[
"✓ Đã xoá dữ liệu {0}.",
"✓ Cleared data of {0}."
],
[
"✗ Không đọc được: {0}",
"✗ Couldn't read: {0}"
],
[
"{0}: +{1} Blue mỗi ngày",
"{0}: +{1} Blue a day"
],
[
"Tối đa {0} 💎 / video",
"Up to {0} 💎 / video"
],
[
"Nạp {0} = {1} lượt quay",
"Top up {0} = {1} spins"
],
[
"🍀 Dùng thêm vé · {0}",
"🍀 Another ticket · {0}"
],
[
"Đổi sang Android {0}",
"Switch to Android {0}"
],
[
"Đã mở bản clone {0}.",
"Opened clone {0}."
],
[
"✗ Chưa mở được {0}: {1}",
"✗ Couldn't open {0}: {1}"
],
[
"✗ Chưa gỡ được {0}: {1}",
"✗ Couldn't uninstall {0}: {1}"
],
[
"{0}%  ·  đang dùng {1}%",
"{0}%  ·  in use {1}%"
],
[
"\n\nTrừ {0} từ số dư?",
"\n\nDeduct {0} from your balance?"
],
[
"   ·   Cần thêm {0}",
"   ·   Need {0} more"
],
[
" · 🍀 vé may mắn {0}",
" · 🍀 lucky ticket {0}"
],
[
"⏰ Thời gian: từ {0}",
"⏰ When: from {0}"
],
[
"  ·  đang dùng {0}%",
"  ·  in use {0}%"
],
[
"gpu: {0} (dùng CPU)",
"gpu: {0} (using CPU)"
],
[
"Số dư hiện tại: {0}",
"Current balance: {0}"
],
[
"Đã tạo đơn {0} máy!",
"Created order for {0} phones!"
],
[
"Đơn giá {0} / ngày",
"Price {0} / day"
],
[
" · còn lại mã {0}%",
" · otherwise a {0}% code"
],
[
"  ·  {0} bản clone",
"  ·  {0} clones"
],
[
"✗ Chưa {0} được {1}: {2}",
"✗ Couldn't {0} {1}: {2}"
],
[
"Đang chuẩn bị {0}…",
"Preparing {0}…"
],
[
"💎 Gia hạn {0} ngày",
"💎 Renew {0} days"
],
[
"còn {0} ngày {1} giờ",
"{0} d {1} h left"
],
[
"còn {0} giờ {1} phút",
"{0} h {1} min left"
],
[
"✓ Giảm {0} → còn {1}",
"✓ {0} off → {1}"
],
[
", giảm tối đa {0}",
", up to {0} off"
],
[
"   ·   Số dư: {0}",
"   ·   Balance: {0}"
],
[
"  ·  lượt mua {0}",
"  ·  bought spin {0}"
],
[
"➕ Quay thêm · {0}",
"➕ Extra spin · {0}"
],
[
"Đang dùng: {0} dp",
"In use: {0} dp"
],
[
"Tạo {0} bản clone",
"Create {0} clones"
],
[
"✓ Đã lưu ảnh: {0}",
"✓ Saved the screenshot: {0}"
],
[
"Cập nhật lỗi: {0}",
"Update failed: {0}"
],
[
"  (đang dùng {0})",
"  (using {0})"
],
[
"nạp {0} dùng thử {1}",
"top up {0}, try {1}"
],
[
"🎡 Quay ngay · {0}",
"🎡 Spin now · {0}"
],
[
"Dùng được đến {0}",
"Valid until {0}"
],
[
"Thuê ngay {0} máy",
"Rent now {0} phones"
],
[
"Đổi Android — {0}",
"Switch Android — {0}"
],
[
"🎫 Mã của bạn: {0}",
"🎫 Your code: {0}"
],
[
"✓ Đã chép mã {0}",
"✓ Copied code {0}"
],
[
"Gia hạn {0} ngày",
"Renew {0} days"
],
[
"Vé may mắn · {0}",
"Lucky ticket · {0}"
],
[
"✅ Đã lưu {0} FPS",
"✅ Saved {0} FPS"
],
[
"Đang đặt {0} dp…",
"Setting {0} dp…"
],
[
"  ·  xin lúc {0}",
"  ·  asked at {0}"
],
[
"Chuyển khoản {0}",
"Transfer {0}"
],
[
"≈ {0} / 30 ngày",
"≈ {0} / 30 days"
],
[
"  Hôm nay: {0}/{1}",
"  Today: {0}/{1}"
],
[
"\n💎 Trả {0} Blue",
"\n💎 Pay {0} Blue"
],
[
"tối đa {0} ngày",
"up to {0} days"
],
[
" · mua lượt {0}",
" · buy a spin {0}"
],
[
"Bắt đầu lúc {0}",
"Starts at {0}"
],
[
"Nạp {0} = {1} lượt",
"Top up {0} = {1} spins"
],
[
"{0} giải · còn {1}",
"{0} prizes · {1} left"
],
[
"Mã của bạn: {0}",
"Your code: {0}"
],
[
"{0} ngày × {1} máy",
"{0} days × {1} phones"
],
[
"{0}% (mặc định)",
"{0}% (default)"
],
[
" · hết hạn {0}",
" · expires {0}"
],
[
"{0}% trúng mã {1}",
"{0}% chance of a {1} code"
],
[
"Vé may mắn {0}",
"Lucky ticket {0}"
],
[
"Đang dừng {0}…",
"Stopping {0}…"
],
[
"✓ Đã dừng {0}.",
"✓ Stopped {0}."
],
[
"{0} ngày liền",
"{0} days in a row"
],
[
"{0} 💎 / tháng",
"{0} 💎 / month"
],
[
"tối thiểu {0}",
"minimum {0}"
],
[
"Từ {0} → mã {1}%",
"From {0} → {1}% code"
],
[
"  ·  🍀 vé {0}",
"  ·  🍀 ticket {0}"
],
[
"Đang gửi {0}…",
"Sending {0}…"
],
[
"Đã có {0} bản",
"Already has {0} copies"
],
[
"bạn có {0} mã",
"you have {0} codes"
],
[
"Công cụ — {0}",
"Tools — {0}"
],
[
"Đổi FPS — {0}",
"Change FPS — {0}"
],
[
"Mua lượt {0}",
"Buy a spin {0}"
],
[
"Mã giảm {0}%",
"{0}% off code"
],
[
"Giữ {0} nhân",
"Keep {0} cores"
],
[
"▶ Mở bản {0}",
"▶ Open copy {0}"
],
[
"Đang mở {0}…",
"Opening {0}…"
],
[
"Đang gỡ {0}…",
"Uninstalling {0}…"
],
[
"✓ Đã mở {0}.",
"✓ Opened {0}."
],
[
"✓ Đã gỡ {0}.",
"✓ Uninstalled {0}."
],
[
"Nâng cấp {0}",
"Upgrade {0}"
],
[
"{0} ngày · ",
"{0} days · "
],
[
"% hoặc {0}%",
"% or {0}%"
],
[
"Lưu {0} FPS",
"Save {0} FPS"
],
[
"Bản mới {0}",
"New version {0}"
],
[
"{0}% hoặc {1}%",
"{0}% or {1}%"
],
[
"Gia hạn {0}",
"Renew {0}"
],
[
" × {0} máy",
" × {0} phones"
],
[
"Đang {0} {1}…",
"{0}: {1}…"
],
[
"✓ Đã {0} {1}.",
"✓ Done: {0} {1}."
],
[
"Số dư: {0}",
"Balance: {0}"
],
[
" · bỏ {0}",
" · dropped {0}"
],
[
" (từ {0})",
" (from {0})"
],
[
"{0}–{1} nhân",
"{0}–{1} cores"
],
[
"{0}–{1} ngày",
"{0}–{1} days"
],
[
" đến {0}.",
" to {0}."
],
[
"Giữ {0}GB",
"Keep {0}GB"
],
[
"Đang {0}…",
"{0}…"
],
[
"{0}/{1} xong",
"{0}/{1} done"
],
[
"Ngày {0}",
"Day {0}"
],
[
"{0} ngày",
"{0} days"
],
[
" {0} máy",
" {0} phones"
],
[
"{0} lượt",
"{0} spins"
],
[
"{0} nhân",
"{0} cores"
],
[
"nhỏ {0}%",
"small {0}%"
],
[
"{0} giờ ",
"{0} hours "
],
[
"Lỗi {0}",
"Error {0}"
],
[
" từ {0}",
" from {0}"
],
[
"{0} giờ",
"{0} hours"
],
[
"Nạp {0}",
"Top up {0}"
],
[
"{0} máy",
"{0} phones"
],
[
"{0} bản",
"{0} copies"
],
[
"{0}đ",
"{0}đ"
]
]

SRV_R = [
[
"Máy chủ chưa lấy được hình của máy này\\. Bấm [“\"]Khởi động lại máy[”\"] để sửa \\(1–2 phút, dữ liệu giữ nguyên\\) — vẫn lỗi thì báo hỗ trợ\\.",
"The server couldn't get this phone's screen. Tap “Restart phone” to fix it (1–2 minutes, your data is kept) — if it still fails, contact support.",
""
],
[
"Máy chưa bật lại được — máy chủ sẽ tự thử lại\\. Bấm [“\"]Khởi động lại máy[”\"] để sửa nhanh; quá 5 phút vẫn vậy thì báo hỗ trợ\\.",
"The phone couldn't be started yet — the server will keep trying. Tap “Restart phone” for a quick fix; if it's still like this after 5 minutes, contact support.",
""
],
[
"🔄 Máy đang được bật lại — khoảng 1–2 phút, đã (\\d+) giây\\. Tự vào khi máy lên\\.",
"🔄 The phone is starting — about 1–2 minutes ({1} s so far). You'll get in automatically when it's up.",
""
],
[
"🔄 Máy đang được bật lại — khoảng 1–2 phút\\. Tự vào khi máy lên\\.",
"🔄 The phone is starting — about 1–2 minutes. You'll get in automatically when it's up.",
""
],
[
"🔄 Máy đang khởi động lại — máy chủ đang bận nên lâu hơn bình thường, đã (\\d+) giây\\. Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào\\.",
"🔄 The phone is restarting — the server is busy, so it's taking longer than usual ({1} s so far). You can leave; it keeps restarting — open it again to get in.",
""
],
[
"🔄 Máy đang khởi động lại — khoảng 1–2 phút, đã (\\d+) giây\\. Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào\\.",
"🔄 The phone is restarting — about 1–2 minutes ({1} s so far). You can leave; it keeps restarting — open it again to get in.",
""
],
[
"🔄 Máy đang khởi động lại — khoảng 1–2 phút\\. Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào\\.",
"🔄 The phone is restarting — about 1–2 minutes. You can leave; it keeps restarting — open it again to get in.",
""
],
[
"Máy đang bật nhưng Android chưa trả lời, đã (\\d+) giây\\. Chờ thêm ít phút, hoặc bấm [“\"]Khởi động lại máy[”\"] để sửa nhanh \\(1–2 phút, dữ liệu giữ nguyên\\)\\.",
"The phone is on but Android isn't responding yet ({1} s). Wait a few more minutes, or tap “Restart phone” for a quick fix (1–2 minutes, your data is kept).",
""
],
[
"Máy đang bật nhưng Android chưa trả lời\\. Chờ thêm ít phút, hoặc bấm [“\"]Khởi động lại máy[”\"] để sửa nhanh \\(1–2 phút, dữ liệu giữ nguyên\\)\\.",
"The phone is on but Android isn't responding yet. Wait a few more minutes, or tap “Restart phone” for a quick fix (1–2 minutes, your data is kept).",
""
],
[
"Máy đang tạm dừng trên máy chủ\\. Bấm [“\"]Khởi động lại máy[”\"] để bật lại; không được thì báo hỗ trợ\\.",
"The phone is paused on the server. Tap “Restart phone” to start it again; if that doesn't work, contact support.",
""
],
[
"Máy chủ chưa có máy này \\(có thể đang được tạo lại\\)\\. Chờ ít phút; vẫn vậy thì báo hỗ trợ kèm tên máy\\.",
"The server doesn't have this phone yet (it may be being recreated). Wait a few minutes; if it stays like this, contact support with the phone's name.",
""
],
[
"💤 Máy đang thức dậy sau khi tự nghỉ \\(lâu không dùng\\) — khoảng 1 phút, đã (\\d+) giây\\.",
"💤 The phone is waking up after resting (unused for a while) — about 1 minute ({1} s so far).",
""
],
[
"💤 Máy đang thức dậy sau khi tự nghỉ \\(lâu không dùng\\) — khoảng 1 phút\\.",
"💤 The phone is waking up after resting (unused for a while) — about 1 minute.",
""
],
[
"Máy chưa thức dậy sau 4 phút — mở lại sau ít phút hoặc báo hỗ trợ\\.",
"The phone hasn't woken up after 4 minutes — reopen it in a few minutes or contact support.",
""
],
[
"Máy chưa lên sau 4 phút — bấm [“\"]Khởi động lại máy[”\"] hoặc báo hỗ trợ\\.",
"The phone isn't up after 4 minutes — tap “Restart phone” or contact support.",
""
],
[
"Máy không còn tồn tại\\.",
"This phone no longer exists.",
""
],
[
"Chủ máy đã tắt chia sẻ hoặc đã chuyển máy — bạn không còn quyền dùng máy này\\.",
"The owner stopped sharing or transferred this phone — you no longer have access.",
""
],
[
"Thiếu mã máy\\.",
"Missing phone ID.",
""
],
[
"Phiên đăng nhập hết hạn, hãy đăng nhập lại\\.",
"Session expired, please log in again.",
""
],
[
"Không tìm thấy máy\\.",
"Phone not found.",
""
],
[
"Đây không phải máy của bạn\\.",
"This isn't your phone.",
""
],
[
"Máy nằm ở máy chủ khác — hãy mở lại\\.",
"This phone is on another server — please reopen it.",
""
],
[
"Máy chưa chạy \\(đang tạo, tạm dừng hoặc đã hết hạn\\)\\.",
"The phone isn't running (being created, paused or expired).",
""
],
[
"Máy chưa sẵn sàng, thử lại sau ít giây\\.",
"The phone isn't ready yet, try again in a few seconds.",
""
],
[
"Máy chưa sẵn sàng\\.",
"The phone isn't ready yet.",
""
],
[
"Máy đang bị khoá: liên hệ hỗ trợ\\.",
"This phone is locked — contact support.",
""
],
[
"Máy đang bị khoá: (.+)",
"This phone is locked: {1}",
""
],
[
"Hệ thống đang bảo trì, quay lại sau ít phút\\.",
"Under maintenance — please come back in a few minutes.",
""
],
[
"Không lấy được hình từ cửa sổ máy — thử mở lại\\.",
"Couldn't get the phone's picture — try reopening it.",
""
],
[
"Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại\\.",
"The phone is off or restarting — wait a few seconds, then reopen it.",
""
],
[
"Máy đang tắt hoặc đang khởi động lại\\.",
"The phone is off or restarting.",
""
],
[
"Máy đang được mở ở nơi khác\\.",
"This phone was opened somewhere else.",
""
],
[
"Đang mở máy ở kết nối khác\\.",
"The phone is being opened on another connection.",
""
],
[
"Màn hình Android của máy này đang lỗi \\(máy chủ không lấy được hình\\)\\. Bấm [“\"]Khởi động lại máy[”\"] để sửa — vẫn lỗi thì báo hỗ trợ\\.",
"This phone's Android screen has a problem (the server can't get the picture). Tap “Restart phone” to fix it — if it still fails, contact support.",
""
],
[
"Máy chủ đang bận — tạm tắt hình xem trước\\.",
"The server is busy — live preview is paused.",
""
],
[
"Máy đang được xem trước ở nhiều nơi\\.",
"This phone is being previewed in too many places.",
""
],
[
"Chưa bật được hình xem trước\\.",
"Couldn't start the live preview.",
""
],
[
"Máy đang nghỉ — mở máy để bật lại\\.",
"The phone is resting — open it to wake it up.",
""
],
[
"Máy chủ chưa bật được hình — thử lại\\.",
"The server couldn't start the picture — retrying.",
""
],
[
"Máy chủ đang bận, thử lại…",
"The server is busy, retrying…",
""
],
[
"Hệ thống đang bảo trì: (.+)\\. Vui lòng quay lại sau\\.",
"Under maintenance: {1}. Please come back later.",
""
],
[
"Hệ thống đang bảo trì\\. Vui lòng quay lại sau\\.",
"Under maintenance. Please come back later.",
""
],
[
"Máy đang bị khoá đến (\\S+ \\S+): (.+)\\. Liên hệ hỗ trợ nếu cần\\.",
"This phone is locked until {1}: {2}. Contact support if needed.",
""
],
[
"Máy đang bị khoá đến (\\S+ \\S+)\\. Liên hệ hỗ trợ nếu cần\\.",
"This phone is locked until {1}. Contact support if needed.",
""
],
[
"Máy đang bị khoá vĩnh viễn: (.+)\\. Liên hệ hỗ trợ nếu cần\\.",
"This phone is locked: {1}. Contact support if needed.",
""
],
[
"Máy đang bị khoá vĩnh viễn\\. Liên hệ hỗ trợ nếu cần\\.",
"This phone is locked. Contact support if needed.",
""
],
[
"Không có chức năng này\\.",
"This feature isn't available.",
""
],
[
"Không được phép\\.",
"Not allowed.",
""
],
[
"Nguồn không được phép\\.",
"Source not allowed.",
""
],
[
"Phiên đăng nhập hết hạn — tải lại trang và đăng nhập lại\\.",
"Session expired — reload and log in again.",
""
],
[
"Không tìm thấy máy của bạn\\.",
"Your phone wasn't found.",
""
],
[
"Máy chưa chạy \\(đang tạo, tạm dừng hoặc đã huỷ\\)\\.",
"The phone isn't running (being created, paused or cancelled).",
""
],
[
"Hãy mở máy từ app hoặc trang web\\.",
"Open the phone from the app or the website.",
""
],
[
"Máy phản hồi quá lâu, thử lại\\.",
"The phone took too long to respond, try again.",
""
],
[
"Không có việc này\\.",
"Job not found.",
""
],
[
"Chỉ admin\\.",
"Admins only.",
""
],
[
"Không có file này\\.",
"File not found.",
""
],
[
"Phím không hợp lệ\\.",
"Invalid key.",
""
],
[
"Chưa nhập chữ\\.",
"No text entered.",
""
],
[
"Chỉ dán được chữ KHÔNG DẤU\\. Chữ có dấu hãy gõ trực tiếp trên màn hình máy\\.",
"Only plain text without accents can be pasted. Type accented text directly on the phone screen.",
""
],
[
"Link phải bắt đầu bằng http:// hoặc https://",
"The link must start with http:// or https://",
""
],
[
"Chưa xoay được — máy chưa sẵn sàng, thử lại sau giây lát\\.",
"Couldn't rotate — the phone isn't ready, try again shortly.",
""
],
[
"Chưa đọc được màn hình máy — thử lại sau giây lát\\.",
"Couldn't read the phone's screen — try again shortly.",
""
],
[
"Chưa lấy được mã — mở Cửa hàng Play 1 lần, đợi 1 phút rồi thử lại\\.",
"Couldn't get the ID yet — open the Play Store once, wait 1 minute, then try again.",
""
],
[
"Không có app này trong kho\\.",
"This app isn't in the store.",
""
],
[
"Tên app không hợp lệ\\.",
"Invalid app name.",
""
],
[
"Tên ứng dụng không hợp lệ\\.",
"Invalid app name.",
""
],
[
"Đã tắt vị trí giả\\.",
"Fake location turned off.",
""
],
[
"Toạ độ không hợp lệ\\.",
"Invalid coordinates.",
""
],
[
"Đổi vị trí GPS cần máy Android 12 trở lên\\.",
"Changing the GPS location needs Android 12 or newer.",
""
],
[
"Đã bỏ các bản clone\\.",
"Clones removed.",
""
],
[
"Chưa có bản clone này — bấm Clone trước\\.",
"This clone doesn't exist yet — tap Clone first.",
""
],
[
"Số bản clone không hợp lệ\\.",
"Invalid number of clones.",
""
],
[
"Máy này chỉ đủ chạy (\\d+) bản clone cho mượt \\(mỗi bản cần \\+3GB RAM, \\+2 nhân\\)\\. Chọn ít bản hơn, hoặc bấm Nâng cấp RAM/CPU\\.",
"This phone can only run {1} clone(s) smoothly (each needs +3GB RAM, +2 cores). Choose fewer, or tap Upgrade RAM/CPU.",
""
],
[
"Máy ([\\d.]+)GB / ([\\d.]+) nhân chưa đủ để chạy thêm .+",
"A {1}GB / {2}-core phone isn't enough for clones (it would freeze). Clone tab needs at least 6GB RAM + 4 cores for 1 clone (+3GB RAM, +2 cores for each extra) — upgrade the phone first.",
""
],
[
"Máy chưa cài app này — cài bản chính trước rồi mới clone\\.",
"This app isn't installed — install the main app first, then clone it.",
""
],
[
"Android trong máy không cho tạo hồ sơ clone\\.",
"Android on this phone doesn't allow clone profiles.",
""
],
[
"Đã mở bản clone (\\d+) của (.+)\\.",
"Opened clone {1} of {2}.",
""
],
[
"Mã tải lên không hợp lệ\\.",
"Invalid upload ID.",
""
],
[
"File rỗng hoặc lớn hơn 4GB\\.",
"The file is empty or larger than 4GB.",
""
],
[
"Server tạm hết dung lượng, thử lại sau\\.",
"The server is out of space, try again later.",
""
],
[
"Lệch vị trí",
"Upload position mismatch",
"j"
],
[
"Dữ liệu vượt kích thước file\\.",
"The data is larger than the file.",
""
],
[
"FPS phải từ (\\d+) đến (\\d+)\\.",
"FPS must be between {1} and {2}.",
""
],
[
"FPS phải từ (\\d+) đến (\\d+)",
"FPS must be between {1} and {2}",
""
],
[
"FPS không hợp lệ\\.",
"Invalid FPS.",
""
],
[
"Máy dưới 4 nhân chỉ chọn tối đa 60 FPS \\(treo game nên để 30 FPS cho mượt\\)\\.",
"Phones under 4 cores can use up to 60 FPS (30 FPS is best for idling games).",
""
],
[
"Máy dưới 4 nhân chỉ chọn tối đa 60 FPS\\.?",
"Phones under 4 cores can use up to 60 FPS.",
""
],
[
"Độ phân giải phải dạng rộng x cao, VD 1080x1920\\.",
"Resolution must be width x height, e.g. 1080x1920.",
""
],
[
"Máy đang được đổi cấu hình, đợi chút\\.",
"The phone's setup is being changed, please wait.",
""
],
[
"Không xác định được máy\\.",
"Couldn't identify the phone.",
""
],
[
"Thiếu bật / tắt root\\.",
"Missing root on / off.",
""
],
[
"Danh sách app không hợp lệ\\.",
"Invalid app list.",
""
],
[
"Đang lưu cấu hình root của máy này, đợi vài giây\\.",
"Saving this phone's root settings, wait a few seconds.",
""
],
[
"Chế độ không hợp lệ\\.",
"Invalid mode.",
""
],
[
"Máy đang bị khoá — mở khoá trước rồi hãy ép khởi động lại\\.",
"The phone is locked — unlock it before forcing a restart.",
""
],
[
"Máy đang khởi động lại / đổi cấu hình — đợi xong rồi thử lại\\.",
"The phone is restarting / changing setup — wait until it's done, then try again.",
""
],
[
"Đang bảo trì\\.",
"Under maintenance.",
""
],
[
"Lỗi máy chủ: .*",
"Server error — try again.",
""
],
[
"Chỉ nhận file \\.apk / \\.apks / \\.apkm / \\.xapk",
"Only .apk / .apks / .apkm / .xapk files are accepted",
""
],
[
"Link không phải file APK\\.",
"The link isn't an APK file.",
""
],
[
"Link không hợp lệ \\(chỉ nhận link http/https công khai\\)\\.",
"Invalid link (public http/https links only).",
""
],
[
"File quá lớn \\(tối đa 4GB\\)\\.",
"File too large (max 4GB).",
""
],
[
"File đã hết hạn, tải lên lại\\.",
"The file expired — upload it again.",
""
],
[
"File gói hỏng hoặc bị mã hoá\\.",
"The package file is corrupted or encrypted.",
""
],
[
"Gói không có file \\.apk bên trong\\.",
"The package has no .apk inside.",
""
],
[
"Link này là TRANG WEB, không phải link tải file\\..*",
"This link is a WEB PAGE, not a file download. Open it on your computer, tap Download, then copy the real download link (usually ending in .apk) and paste it here — or download the file and use “Upload file / APK”.",
""
],
[
"Không tải được từ Google Drive — hãy chia sẻ file ở chế độ [“\"]Bất kỳ ai có đường liên kết[”\"]\\.",
"Couldn't download from Google Drive — share the file as “Anyone with the link”.",
""
],
[
"Độ rộng nhỏ nhất phải từ 240 đến 1600 dp\\.",
"Smallest width must be between 240 and 1600 dp.",
""
],
[
"Độ rộng nhỏ nhất không hợp lệ\\.",
"Invalid smallest width.",
""
],
[
"Máy chủ chưa cập nhật bản có Root theo app — báo admin cập nhật\\.",
"The server doesn't support per-app root yet — ask an admin to update it.",
""
],
[
"Không lưu được cấu hình root, thử lại sau\\.",
"Couldn't save root settings, try again later.",
""
],
[
"Cấu hình root đọc được bị lỗi\\.",
"The root settings are corrupted.",
""
],
[
"Không chụp được màn hình\\.",
"Couldn't take a screenshot.",
""
],
[
"Máy hết bộ nhớ — xoá bớt file / gỡ bớt app rồi thử lại\\.",
"The phone is out of storage — delete some files or apps and try again.",
""
],
[
"Máy chủ của máy này chưa có tính năng này — đang được cập nhật, thử lại sau\\.",
"This phone's server doesn't have this feature yet — try again later.",
""
],
[
"Đang khởi động Android \\(1–3 phút\\)…",
"Starting Android (1–3 minutes)…",
""
],
[
"Đang tắt hẳn máy \\(máy treo thì tắt cưỡng bức\\)…",
"Shutting the phone down fully (force-stopping it if frozen)…",
""
],
[
"Máy đã khởi động lại xong\\.",
"The phone has restarted.",
""
],
[
"Máy đã khởi động, đang kết nối lại…",
"The phone has started, reconnecting…",
""
],
[
"Máy đã bật lại, đang kết nối….*",
"The phone is back on, connecting…",
""
],
[
"Đã ép khởi động lại xong.*",
"Forced restart done.",
""
],
[
"Đang kiểm tra / bật root \\(máy có thể khởi động lại ~1 phút\\)…",
"Checking / enabling root (the phone may restart, ~1 minute)…",
""
],
[
"✅ Máy đã ROOT\\. Tool cần root \\(gọi lệnh su\\) dùng được ngay, không cần khởi động lại\\.",
"✅ The phone is ROOTED. Tools that need root (su) work right away, no restart needed.",
""
],
[
"⏳ Máy đang bật root, chờ 1 phút rồi bấm lại\\.",
"⏳ Root is being enabled — wait 1 minute, then tap again.",
""
],
[
"Đang bật root cho app đã chọn… \\(máy chưa có root gốc sẽ tự khởi động lại ~1 phút\\)",
"Enabling root for the selected apps… (a phone without base root restarts, ~1 minute)",
""
],
[
"Đang tắt root…",
"Turning root off…",
""
],
[
"Đã lưu\\.",
"Saved.",
"j"
],
[
"Máy đang khởi động lại với chế độ mới \\(khoảng 1–2 phút\\)…",
"Restarting the phone with the new mode (about 1–2 minutes)…",
""
],
[
"Đã chuyển sang MƯỢT\\.",
"Switched to SMOOTH.",
""
],
[
"Đã chuyển sang HIỆN 3D\\.",
"Switched to 3D DISPLAY.",
""
],
[
"Đã đổi, đang kết nối lại…",
"Changed, reconnecting…",
""
],
[
"Đang áp dụng và khởi động lại máy \\(1–3 phút\\)…",
"Applying and restarting the phone (1–3 minutes)…",
""
],
[
"Đang đổi kích thước màn hình…",
"Changing the screen size…",
""
],
[
"Đã đổi sang (\\S+) · (\\d+) FPS\\. Dữ liệu vẫn giữ nguyên\\.",
"Changed to {1} · {2} FPS. Your data is kept.",
""
],
[
"Đã đổi sang (\\S+) — app đang chạy vẫn giữ nguyên\\.",
"Changed to {1} — running apps keep running.",
""
],
[
"Đang tạo (\\d+) bản clone \\(mỗi bản ~20 giây\\)…",
"Creating {1} clone(s) (~20 s each)…",
""
],
[
"✅ Đã có (\\d+) bản clone! Mở lại Clone tab.*",
"✅ {1} clone(s) ready! Reopen Clone tab and tap ▶ Open clone 1, 2… to run them (or use the Work tab in the app list).",
""
],
[
"✅ Đã có (\\d+) bản clone! Trên màn hình chính máy.*",
"✅ {1} clone(s) ready! The phone's home screen has whale icons “Clone 1”, “Clone 2”… — tap one to open it.",
""
],
[
"Đã có (\\d+) bản clone\\. Máy cần KHỞI ĐỘNG LẠI 1 lần.*",
"{1} clone(s) exist. The phone needs ONE restart to add more — tap “Restart”, then clone again.",
""
],
[
"Đã có (\\d+) bản clone — máy này chỉ cho tối đa.*",
"{1} clone(s) exist — that's the most this phone allows. For more accounts, rent another phone.",
""
],
[
"Đã đặt vị trí (.+)\\. Mở lại app cần vị trí để nhận vị trí mới\\.",
"Location set to {1}. Reopen apps that use location to get the new one.",
""
],
[
"✅ Đã cài (.+) — mở trên màn hình chính của máy\\.",
"✅ Installed {1} — open it from the phone's home screen.",
""
],
[
"Đã cài xong (.+?)( \\(kèm (\\d+) file dữ liệu game\\))?",
"Installed {1}",
"j"
],
[
"✅ Đã cài (.+)",
"✅ Installed {1}",
"j"
],
[
"Đang cài (.+)",
"Installing {1}",
"j"
],
[
"Đã lưu vào thư mục Download: (.+)",
"Saved to the Download folder: {1}",
""
],
[
"Đã tải (.+)",
"Downloaded {1}",
"j"
],
[
"Không lấy được (.+) từ trang chính chủ \\(.*\\)\\. Thử lại sau ít phút\\.",
"Couldn't download {1} from the official site. Try again in a few minutes.",
""
],
[
"Không khởi động lại được: .*",
"Couldn't restart the phone — try again in a minute or contact support.",
""
],
[
"Không ép khởi động lại được: .*",
"Couldn't force-restart the phone — try again in a minute or contact support.",
""
],
[
"Chưa khởi động lại được: .*",
"Couldn't restart yet — try again in a minute.",
""
],
[
"Không đổi được: .*",
"Couldn't change it — try again later.",
""
],
[
"Đổi cấu hình lỗi: .*",
"Couldn't change the setup — try again later.",
""
],
[
"Chưa root được: .*",
"Couldn't root the phone — try again later.",
""
],
[
"Không đọc được cấu hình root: .*",
"Couldn't read the root settings.",
""
],
[
"Chưa clone được: .*",
"Couldn't clone — try again later.",
""
],
[
"Chưa mở được bản clone: .*",
"Couldn't open the clone.",
""
],
[
"Chưa đặt được vị trí: .*",
"Couldn't set the location.",
""
],
[
"Cài APK lỗi: .*",
"Couldn't install the APK.",
""
],
[
"Không chép được file vào máy: .*",
"Couldn't copy the file to the phone.",
""
],
[
"Không chép được file: .*",
"Couldn't copy the file.",
""
],
[
"Khởi động lại",
"Restart",
"j"
],
[
"Ép khởi động lại",
"Forced restart",
"j"
],
[
"Root máy",
"Root phone",
"j"
],
[
"Đổi chế độ hình",
"Change display mode",
"j"
],
[
"Cài (.+)",
"Install {1}",
"j"
]
]


# ===================================================================================================== dịch lúc chạy
_VN = re.compile("[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.I)
_AMT = re.compile(r"\d[\d.,]*\s?đ")                                  # "290đ", "50.000 đ" không tính là chữ Việt


def has_vi(s):
    if not s or str(s).strip() == "đ": return False                       # "đ" (đơn vị tiền) đứng riêng
    return bool(_VN.search(_AMT.sub("", str(s))))


_PH = re.compile(r"(\{\d+\}|\{\{|\}\})")
_FILL = re.compile(r"\{(\d+)\}")


def _compile(vi):
    rx, order, lits = [], [], []
    for x in _PH.split(vi):
        if not x: continue
        if x == "{{": rx.append(r"\{"); lits.append("{")
        elif x == "}}": rx.append(r"\}"); lits.append("}")
        elif x[0] == "{" and x[-1] == "}" and x[1:-1].isdigit(): rx.append("(.*?)"); order.append(int(x[1:-1]))
        else: rx.append(re.escape(x)); lits.append(x)
    key = max(lits, key=len) if lits else ""
    letters = len(re.sub(r"[\W\d_]", "", "".join(lits)))
    plain = not has_vi("".join(lits))                                    # chữ cố định không dấu ("{0}/{1} xong") → thử cả khi câu không có dấu
    head = len(order) == 1 and rx[-1] == "(.*?)" and lits and len(re.sub(r"[\W\d_]", "", lits[0])) >= 5 and vi.find("{") > 0
    strong = letters >= 10 or bool(head)                                 # mẫu "mạnh" → phần thay đổi chưa dịch được (tên máy…) vẫn nhận
    return re.compile("".join(rx), re.S), order, key, strong, plain


_T = None
_S = None



# ---- 22/11 · 🌐 Proxy riêng của máy (thêm tay: bộ sinh pc/i18n chưa có các câu này) ----
EXACT.update({
"Proxy riêng của máy": "This phone's proxy",
"🌐 Proxy riêng của máy…": "🌐 This phone's proxy…",
"Mọi app trong máy đi Internet qua proxy của bạn. Proxy chết hoặc sai mật khẩu → máy tự đi mạng thường (không mất mạng), proxy sống lại thì tự dùng lại.": "Every app on the phone goes online through your proxy. If the proxy is down or the password is wrong, the phone falls back to the normal network (it never loses Internet) and switches back when the proxy works again.",
"Proxy mới": "New proxy",
"Tự nhận": "Auto",
"Dán 1 trong các dạng: IP:Port · IP:Port:User:Pass · User:Pass@IP:Port · socks5://… · http://… — “Tự nhận” tự thử SOCKS5 rồi HTTP.": "Paste one of: IP:Port · IP:Port:User:Pass · User:Pass@IP:Port · socks5://… · http://… — “Auto” tries SOCKS5, then HTTP.",
"Lưu & bật": "Save",
"Áp dụng lại": "Re-apply",
"Tắt proxy": "Turn off",
"Web, app và game kết nối TCP đi qua proxy; gọi video / game dùng UDP vẫn đi mạng máy chủ. Đổi Android là máy mới — nhập lại proxy.": "Web, apps and games over TCP go through the proxy; video calls / UDP games still use the server's network. Switching Android creates a new phone — enter the proxy again.",
"Dán proxy vào ô trước (vd 1.2.3.4:8080:user:pass).": "Paste the proxy first (e.g. 1.2.3.4:8080:user:pass).",
"Proxy phải có dạng IP:Port hoặc IP:Port:User:Pass (không có dấu cách).": "The proxy must look like IP:Port or IP:Port:User:Pass (no spaces).",
"Tắt proxy? Máy quay về mạng của máy chủ.": "Turn the proxy off? The phone goes back to the server's network.",
"Đang bật proxy…": "Turning the proxy on…",
})
SRV_R += [
["Chỉ chủ máy mới xem / đặt được proxy của máy này\\.", "Only the phone's owner can view or set its proxy.", ""],
["Đã thu nhỏ (.+) \\(bản clone\\) \\((\\d+) tab nhỏ\\)\\..*", "Minimized {1} (clone) ({2} small tabs). Drag the top bar to move it, drag an edge to resize.", ""],
["Đã thu nhỏ (.+) \\((\\d+) tab nhỏ\\)\\..*", "Minimized {1} ({2} small tabs). Drag the top bar to move it, drag an edge to resize.", ""],
["Đã xếp (\\d+) tab nhỏ \\((\\d+) cột × (\\d+) hàng\\)\\. Màn nhỏ nên.*", "Arranged {1} small tabs ({2} × {3}). The screen is small, so they overlap — raise 📐 Smallest width (e.g. 600 dp) so they don't.", ""],
["Đã xếp (\\d+) tab nhỏ \\((\\d+) cột × (\\d+) hàng\\)\\.", "Arranged {1} small tabs ({2} × {3}).", ""],
["Đã phóng to (.+) \\(bản clone\\) ra toàn màn\\.", "{1} (clone) is full screen again.", ""],
["Đã phóng to (.+) ra toàn màn\\.", "{1} is full screen again.", ""],
["Đã phóng to (.+) hết màn\\. .*", "{1} now fills the screen. For true full screen, click ▭ on the window's title bar.", ""],
["Chưa có app nào đang mở toàn màn — .*", "No app is open full screen — open an app (e.g. Roblox), then click Minimize tab.", ""],
["Các tab đang là cửa sổ nhỏ rồi — .*", "Your tabs are already small windows — open another tab (e.g. a clone), then click Minimize tab.", ""],
["Máy chưa bật được cửa sổ nhỏ — .*", "Small windows aren't on yet on this phone — restart it once, then try again.", ""],
["Chưa có tab nhỏ nào — .*", "No small tabs yet — open an app and click Minimize tab first.", ""],
["Chưa có tab nhỏ nào đang hiện trên màn hình\\.", "No small tab is on the screen.", ""],
["Android của máy này quá cũ, chưa có cửa sổ nhỏ\\.", "This phone's Android is too old for small windows.", ""],
["Android của máy này chưa đọc được danh sách tab — .*", "Couldn't read this phone's tabs — try again in a moment.", ""],
["Đang xếp tab của máy này, đợi vài giây\\.", "Arranging this phone's tabs — wait a few seconds.", ""],
["Thiếu việc cần làm \\(thu nhỏ / sắp xếp / phóng to\\)\\.", "Missing action (minimize / arrange / maximize).", ""],
["Máy chủ chưa cập nhật bản có Proxy — báo admin cập nhật\\.", "The server doesn't support proxies yet — ask an admin to update it.", ""],
["Không đọc được proxy của máy, thử lại sau\\.", "Couldn't read this phone's proxy, try again later.", ""],
["Đọc proxy bị lỗi, thử lại sau\\.", "Reading the proxy failed, try again later.", ""],
["Thiếu việc cần làm \\(lưu / tắt / áp dụng lại\\)\\.", "Missing action (save / turn off / apply again).", ""],
["Proxy không hợp lệ\\.", "Invalid proxy.", ""],
["Kiểu proxy không hợp lệ\\.", "Invalid proxy type.", ""],
["Đang áp dụng proxy cho máy này, đợi vài giây\\.", "Applying this phone's proxy, wait a few seconds.", ""],
["Đang bật proxy \\(kiểm tra proxy \\+ gắn vào máy, ~10–30 giây\\)…", "Turning the proxy on (checking it and attaching it to the phone, ~10–30 s)…", ""],
["Đang tắt proxy…", "Turning the proxy off…", ""],
["Đang áp dụng lại proxy…", "Applying the proxy again…", ""],
["Không áp dụng được proxy, thử lại sau\\.", "Couldn't apply the proxy, try again later.", ""],
["Kiểu proxy phải là Tự nhận / SOCKS5 / HTTP\\.", "The proxy type must be Auto / SOCKS5 / HTTP.", ""],
["Chưa nhập proxy\\.", "No proxy entered.", ""],
["Proxy có ký tự lạ\\.", "The proxy contains invalid characters.", ""],
["Chưa hỗ trợ proxy HTTPS \\(mã hoá tới proxy\\) — dùng HTTP hoặc SOCKS5\\.", "HTTPS proxies (encrypted to the proxy) aren't supported — use HTTP or SOCKS5.", ""],
["Thiếu cổng — nhập dạng IP:cổng hoặc IP:cổng:user:pass\\.", "Missing port — use IP:port or IP:port:user:pass.", ""],
["Cổng proxy phải là số \\(1–65535\\)\\.", "The proxy port must be a number (1–65535).", ""],
["Cổng proxy phải từ 1 đến 65535\\.", "The proxy port must be between 1 and 65535.", ""],
["Chưa hỗ trợ proxy IPv6 — dùng địa chỉ IPv4 hoặc tên miền\\.", "IPv6 proxies aren't supported — use an IPv4 address or a domain name.", ""],
["Địa chỉ proxy không hợp lệ \\(IP hoặc tên miền\\)\\.", "Invalid proxy address (IP or domain name).", ""],
["Địa chỉ proxy không hợp lệ\\.", "Invalid proxy address.", ""],
["User / mật khẩu proxy quá dài hoặc có ký tự lạ\\.", "The proxy user / password is too long or has invalid characters.", ""],
["Máy chưa đặt proxy\\.", "This phone has no proxy set.", ""],
["Đã tắt proxy\\.", "Proxy turned off.", ""],
["Đã lưu — máy đang tắt, proxy tự bật khi máy bật\\.", "Saved — the phone is off; the proxy turns on when it starts.", ""],
["Máy không dùng proxy — đang đi mạng thường\\.", "This phone isn't using a proxy — it's on the normal network.", ""],
["Đã TẮT proxy — máy đi mạng thường\\.", "Proxy turned OFF — the phone uses the normal network.", ""],
["Máy không cho máy chủ quyền root để tắt proxy — khởi động lại máy là proxy tự tắt\\.", "The phone didn't give the server root to turn the proxy off — restarting the phone turns it off.", ""],
["Không tìm được IP của proxy (.+) — kiểm tra lại địa chỉ\\.", "Couldn't find the IP of proxy {1} — check the address.", ""],
["Máy chưa có quyền root cho máy chủ \\(cần để bật proxy\\) — bấm 🔓 Root máy rồi thử lại\\.", "The phone hasn't given the server root (needed for the proxy) — tap 🔓 Root phone, then try again.", ""],
["Máy không cho máy chủ quyền root — chưa bật được proxy\\.", "The phone didn't give the server root — the proxy isn't on yet.", ""],
["Đã BẬT proxy — IP ra: (\\S+) · (\\d+) ms", "Proxy ON — exit IP: {1} · {2} ms", ""],
["Đã lưu proxy nhưng proxy CHƯA dùng được \\((.+)\\) — máy đang đi mạng thường, tự thử lại mỗi 15 giây\\.", "Proxy saved, but it does NOT work yet ({1}) — the phone uses the normal network and retries every 15 s.", ""],
["Chưa bật được proxy: (.+)", "Couldn't turn the proxy on: {1}", ""],
["Chưa áp dụng được: (.+)", "Couldn't apply it yet: {1}", ""],
]


def _tpl():
    global _T
    if _T is None:
        out, extra = [], []
        for vi, en in TPL:
            try: out.append(_compile(vi) + (en,))
            except re.error: continue
            if vi.strip() != vi and vi.strip():                            # bản bỏ khoảng trắng / xuống dòng 2 đầu (dùng khi tách từng dòng)
                try: extra.append(_compile(vi.strip()) + (en.strip(),))
                except re.error: pass
        _T = out + extra
    return _T


def srv_find(s):
    """Câu máy chủ (lỗi, tiến độ việc…) → tiếng Anh, theo bảng chung với web / app Android."""
    global _S
    if _S is None:
        out = []
        for r in SRV_R:
            try: out.append((re.compile(r[0], re.S), r[1]))
            except re.error: pass
        _S = out
    t = (s or "").strip()
    if not t: return None
    for p, en in _S:
        m = p.fullmatch(t)
        if not m: continue
        for g in range(9, 0, -1): en = en.replace("{%d}" % g, (m.group(g) or "") if g <= p.groups else "")
        return en
    return None


_PL = re.compile(r"(?<![\d.,])1 (more )?(phones|days|hours|spins|copies|cores|clones|prizes|videos|tabs|codes|minutes|views|tickets|seconds)\b")
_ONE = {"phones": "phone", "days": "day", "hours": "hour", "spins": "spin", "copies": "copy", "cores": "core", "clones": "clone", "prizes": "prize",
        "videos": "video", "tabs": "tab", "codes": "code", "minutes": "minute", "views": "view", "tickets": "ticket", "seconds": "second"}


def _one(s): return _PL.sub(lambda m: "1 " + (m.group(1) or "") + _ONE[m.group(2)], s)


_SYM = re.compile(r"([^\w(“\"']+)(\w.*)$", re.S)
_XS = None


def _strip_exact():
    """Câu có khoảng trắng / xuống dòng ở 2 đầu ("\n\nTrừ…", "  💎 Trả bằng Blue") → thêm bản đã bỏ 2 đầu."""
    global _XS
    if _XS is None:
        _XS = {}
        for a, b in EXACT.items():
            if a.strip() != a and a.strip() and a.strip() not in EXACT: _XS.setdefault(a.strip(), b.strip())
    return _XS


def _vcount(s): return len(_VN.findall(_AMT.sub("", s)))


def _part(g, sep, depth):
    """1 dòng / 1 đoạn của câu dài: dịch riêng; không được thì thử kèm dấu ngăn phía trước (mảnh gốc kiểu " · được chia sẻ", "\nLưu ý: …")."""
    t = _tr(g, depth + 1, True)
    if t is not None and not has_vi(t): return t
    if sep:
        t2 = _tr(sep + g, depth + 1, True)
        if t2 is not None and t2.startswith(sep) and not has_vi(t2): return t2[len(sep):]
    return t


def _tr(s, depth, strict=False):
    """strict = đang dịch 1 phần của câu ghép: chỉ nhận câu khớp nguyên (không dịch nửa vời từng dòng / từng đoạn)."""
    v = EXACT.get(s)
    if v is not None: return v
    a = len(s) - len(s.lstrip()); b = len(s.rstrip()); lead, k, trail = s[:a], s[a:b], s[b:]
    if not k: return None
    if k != s:
        v = EXACT.get(k)
        if v is not None: return lead + v + trail
    v = _strip_exact().get(k)
    if v is not None: return lead + v + trail
    if depth > 3: return None
    vi = has_vi(k)
    best = None                                                            # (số chữ Việt còn lại, câu) — chọn câu dịch được nhiều nhất
    for cand, pre, post in ((s, "", ""), (k, lead, trail)) if k != s else ((s, "", ""),):
        for rx, order, key, strong, plain, en in _tpl():
            if (not vi and not plain) or (key and key not in cand): continue
            m = rx.fullmatch(cand)
            if not m: continue
            vals, ok, raw = {}, True, False
            for gi, idx in enumerate(order):
                g = m.group(gi + 1) or ""
                if has_vi(g):
                    t = _tr(g, depth + 1, True)
                    if t is None or has_vi(t):
                        if not strong: ok = False; break
                        t = g if t is None else t; raw = True             # tên máy / tên app khách đặt… → giữ nguyên
                    g = t
                vals[idx] = g
            if not ok: continue
            out = pre + _FILL.sub(lambda m_: vals.get(int(m_.group(1)), ""), en) + post
            if not raw: return out
            sc = _vcount(out)
            if best is None or sc < best[0]: best = (sc, out)
    if not vi:                                                             # không dấu: chỉ còn trường hợp 1 dòng / 1 đoạn là câu có sẵn ("30 FPS\ntreo game")
        if strict or best: return best[1] if best else None
        for sep in ("\n", "  ·  ", " · "):
            if sep in k:
                out, hit = [], 0
                for g in s.split(sep):
                    a_ = len(g) - len(g.lstrip()); b_ = len(g.rstrip()); t = EXACT.get(g[a_:b_])
                    out.append(g if t is None else g[:a_] + t + g[b_:]); hit += t is not None
                if hit: return sep.join(out)
        return None
    v = srv_find(k)
    if v is not None: return lead + v + trail
    m = _SYM.match(k)
    if m:                                                                  # ký hiệu đầu câu ("✓  ", "● ", "⏱ ", "• ", "🎁  ") + câu có trong bảng
        t = _tr(m.group(2), depth + 1, True)
        if t is not None and not has_vi(t): return lead + m.group(1) + t + trail
    if strict: return best[1] if best else None
    if "\n" in k:                                                         # nhiều dòng: dòng nào dịch được thì dịch
        out, hit = [], 0
        for i, ln in enumerate(s.split("\n")):
            t = _part(ln, "\n" if i else "", depth) if ln.strip() and has_vi(ln) else None
            out.append(ln if t is None else t); hit += t is not None
        if hit:
            o = "\n".join(out); sc = _vcount(o)
            if best is None or sc < best[0]: best = (sc, o)
    else:
        for sep in ("  ·  ", " · ", " — "):                                # đoạn ghép bằng " · " / " — "
            if sep in k:
                out, hit = [], 0
                for i, g in enumerate(s.split(sep)):
                    t = _part(g, sep if i else "", depth) if g.strip() and has_vi(g) else None
                    out.append(g if t is None else t); hit += t is not None
                if hit:
                    o = sep.join(out); sc = _vcount(o)
                    if best is None or sc < best[0]: best = (sc, o)
                    break
    return best[1] if best else None


_CACHE = {}


def tr(s):
    """Chữ tiếng Việt sắp hiện cho khách → tiếng Anh (không khớp → trả nguyên)."""
    if not isinstance(s, str) or not s: return s
    r = _CACHE.get(s)
    if r is not None: return r
    try: out = _tr(s, 0)
    except Exception: out = None
    out = s if out is None else _one(out)
    if len(_CACHE) > 8000: _CACHE.clear()
    _CACHE[s] = out
    return out


# ===================================================================================================== gắn vào Tk
_KEYS = ("text", "label", "title", "message", "detail")
_ON = False


def _tx1(d):
    if not isinstance(d, dict): return d
    new = None
    for k in _KEYS:
        v = d.get(k)
        if isinstance(v, str) and v:
            t = tr(v)
            if t != v:
                if new is None: new = dict(d)
                new[k] = t
    ft = d.get("filetypes")
    if ft:
        try:
            nf = tuple((tr(x[0]) if isinstance(x[0], str) else x[0],) + tuple(x[1:]) for x in ft)
            if new is None: new = dict(d)
            new["filetypes"] = nf
        except Exception: pass
    return d if new is None else new


def _tx(c):
    if isinstance(c, dict): return _tx1(c)
    if isinstance(c, (tuple, list)): return type(c)(_tx1(x) if isinstance(x, dict) else x for x in c)
    return c


def install():
    """Bật tiếng Anh cho mọi cửa sổ Tk của tiến trình này: chữ trên nhãn / nút / menu / hộp thoại / tiêu đề đi qua tr()."""
    global _ON
    if _ON: return
    import tkinter as tk
    o_opt, o_title = tk.Misc._options, tk.Wm.wm_title

    def _options(self, cnf, kw=None):
        try:
            cnf = _tx(cnf)
            if kw: kw = _tx(kw)
        except Exception: pass
        return o_opt(self, cnf, kw)

    def wm_title(self, string=None):
        if isinstance(string, str): string = tr(string)
        return o_title(self, string)

    tk.Misc._options = _options
    tk.Wm.wm_title = wm_title; tk.Wm.title = wm_title
    _ON = True
