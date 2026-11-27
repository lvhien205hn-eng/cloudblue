# -*- coding: utf-8 -*-
# sua-tat-ca.py — 16/11 · SỬA MỘT LẦN CHO CẢ MÁY CHỦ WINDOWS. Mỗi máy chủ dán 1 lệnh ngắn: lệnh tải file này từ GitHub rồi chạy.
#   1. Cập nhật bản sửa từ GitHub (kiểm kỹ trước khi thay, giữ bản cũ *.truoc-2111a):
#        27/11g — CBVIDEO BẬT CHO MỌI MÁY ANDROID 9 (đã kiểm máy thật: ra hình, xoay ngang / dọc, 0 bỏ khung, 0 bật lại bộ nén). Thông số
#                 web hiện "cbvideo: màn ảo → nạp → ra … khung/s · đọc hình … ms · đổi màu … ms". Web ?cbv=0 = scrcpy để so.
#        27/11f — ANDROID 9 LẤY HÌNH BẰNG CBVIDEO: scrcpy trên Android 9 chỉ ~15 khung/giây vì bộ nén tự đọc ngược hình từ GPU trong
#                 luồng nén (đo CI simpleperf). bluestream tải windows/cbvideo.jar (md5 ghim) → đọc hình song song với nén (+50% khung/giây
#                 trên máy ảo CI) + xin khung khoá tức thì (bỏ khung không còn đứng hình chờ bật lại bộ nén). Lỗi → tự quay về scrcpy.
#                 Chỉ máy Android 9 (LDPlayer); máy MuMu không đổi. Tắt: STREAM_A9_CBVIDEO=0 trong cloudphone.conf.
#        27/11e — ANDROID 9 (LDPlayer 9) MƯỢT NHƯ 12 / 15: bộ nén trong máy LD9 không có khung khoá định kỳ (đo trên máy ảo Android 9
#                 thật) → lỡ bỏ 1 khung là đứng hình tới khi bật lại bộ nén (2–3 giây). bluestream: hình Android 9 ≤ 960 (+40–50% khung/giây,
#                 trừ mức Nét), khung I thưa, bỏ khung → bật lại bộ nén ngay, khó bỏ khung oan, không dumpsys sau mỗi cú bấm; Thông số
#                 hiện "bộ nén Android ra … khung/s" + bỏ khung vì đâu. Phát hình bật lại ~10 giây; máy MuMu phần hình không đổi.
#                 phonectl: máy MuMu gộp đủ 2 tiến trình MuMuVMMHeadless mỗi máy khi tính % card đồ hoạ (hết báo nhầm "Ngoài máy khách:
#                 MuMuVMMHeadless.exe …" trên web, chia đều card tính đúng từng máy).
#        23/11f — 🛠 QUẢN LÝ MÁY CHỦ TỪ WEB + TỰ CẬP NHẬT. Lệnh này ghi kết quả vào logs/cap-nhat.json (bản đang chạy, cập nhật sạch không);
#                 cloudphoned báo lên web → thẻ máy chủ hiện bản đang chạy. Web admin › thẻ máy chủ › 🛠 Quản lý: ⬆ Cập nhật (chạy chính lệnh
#                 này kiểu `--tu-dong`: chỉ thay file + bật lại dịch vụ, KHÔNG kiểm / sửa máy khách), 📋 Danh sách máy, 🖼 Ảnh nền, 🙈 Ẩn cửa sổ,
#                 🧪 Tạo máy thử, ⚡ Tối ưu Windows, ⚡ Khởi động lại / ⏻ Tắt máy chủ, ♻ Làm mới máy, 🧹 Dọn giả lập (việc lớn phải gõ mã máy
#                 chủ). TỰ THEO: 1 máy chủ chạy ổn bản mới đủ lâu (web đặt, mặc định 20 phút) → các máy chủ khác tự cập nhật, chỉ khi bản
#                 trên GitHub đúng là bản đó; tắt riêng 1 máy: TU_CAP_NHAT=0 trong cloudphone.conf. phonectl có thêm lệnh shutdownserver.
#                 Cập nhật cloudphoned + cpapi + phonectl (máy khách KHÔNG tắt).
#        23/11e — 🗗 TAB CỬA SỔ NHỎ đợt 5 — CỬA SỔ NHỎ NẰM ĐÚNG CHỖ trên Android 12+ (đo trên máy MuMu Android 12 thật sau bản 23/11d: tab thứ 2
#                 bị vẽ đè lên tab đầu, kéo thanh tiêu đề hình không chạy theo). Gốc: từ Android 12 bên đặt chỗ hình của cửa sổ nổi là giao diện
#                 hệ thống, mà nó chỉ làm việc đó nếu cửa sổ nổi đã bật LÚC NÓ KHỞI ĐỘNG — máy bật cài đặt sau khi đã mở máy thì không ai đặt
#                 chỗ. cpapi tự đọc chỗ thật của hình, lệch khung tab thì bật lại giao diện hệ thống 1 lần (app / game không tắt). Cập nhật cpapi.
#        23/11d — 🗗 TAB CỬA SỔ NHỎ đợt 4 — GAME VỪA KHUNG THẬT + XOAY MÀN THẬT (đo trên máy MuMu Android 12 thật): game kiểu cũ được MỞ LẠI
#                 NGAY TRONG tab của nó sau khi cửa sổ đã đúng chỗ + cỡ (am kill giữ tab → mở sạch vào đúng tab) → vẽ vừa cửa sổ; lần đầu thu nhỏ
#                 trên màn 360 dp tự bật màn rộng 600 dp; cửa sổ đúng tỉ lệ hình game 16:9. Nút Xoay / Màn ngang rộng: máy bỏ qua khoá xoay
#                 (MuMu) → cpapi cài app trợ giúp vn.cloudblue.xoay (nằm sẵn trong cpapi.py) đặt cửa sổ phủ ép màn ngang.
#                 Kiểu "Android tự thu nhỏ hình" của bản 23/11b–c: máy MuMu Android 12 thật vẽ cửa sổ kiểu đó lệch lên góc trên trái → Android
#                 12L trở xuống ép app đổi cỡ được + mở lại game ngay trong tab (bù thanh tiêu đề lúc mở lại); Android 13+ (máy MuMu Android 15
#                 thật thu hình đúng chỗ) giữ kiểu thu hình, game không phải mở lại. Cập nhật cpapi + phonectl.
#        23/11c — 🗗 TAB CỬA SỔ NHỎ đợt 3 (khách clone nhiều tab): nút Cửa sổ to hơn / nhỏ hơn (cửa sổ trên cùng to / nhỏ 25 %, giữ tỉ lệ) +
#                       🖥 Màn ngang rộng (độ rộng nhỏ nhất 600 dp + khoá ngang → màn chính nằm ngang, xếp được nhiều tab) / Màn dọc như cũ.
#                       Chỉ cập nhật cpapi (bật lại ~2 giây); máy khách KHÔNG tắt.
#        23/11b — 🗗 TAB CỬA SỔ NHỎ đợt 2: GAME VỪA KHUNG + TAB NỀN ỔN ĐỊNH. Máy Android 12L / 13 / 14 / 15: không ép game đổi cỡ nữa → thu
#                       nhỏ tab thì Android thu nhỏ CẢ HÌNH game vừa cửa sổ (không tràn viền; game mở sau khi đặt là vừa ngay). Android 10–15:
#                       nút mới 🖼 "Mở lại vừa khung" (cpapi do=refit) mở lại game ngay trong cửa sổ cho game vẽ đúng cỡ (game khởi động lại;
#                       Android 9 báo chưa hỗ trợ, không tắt game). Tab nhỏ
#                       bị app khác che: miễn tối ưu pin / nhóm đang dùng / cho chạy nền, đưa lên lại bằng `am task focus` (không gửi lệnh
#                       mở cho game), phonectl giữ tới 64 app chạy nền. Cập nhật cpapi (bật lại ~2 giây) + phonectl; máy khách KHÔNG tắt.
#        23/11a — 🗗 TAB CỬA SỔ NHỎ (như Redfinger): cpapi bản 23/11a có /cpapi/<máy>/win — khách bấm "Thu nhỏ tab" (web / app) → app đang
#                       mở (VD Roblox, bản clone) thành cửa sổ nổi ngay trên màn hình máy, vẫn chạy + điều khiển được; kéo thanh trên cùng để dời,
#                       kéo mép để đổi cỡ; "Sắp xếp tab" xếp mọi cửa sổ thành lưới; "Phóng to tab" trả về toàn màn. Chỉ cập nhật cpapi
#                       (bật lại ~2 giây, máy khách KHÔNG tắt). Máy Android 9 chưa từng khởi động lại từ 17/11 → khách bấm Khởi động lại 1 lần.
#        22/11b — ▦ XEM TẤT CẢ VPS GPU: trạm máy PC (pcrelay.py 22/11b) nhận Ô XEM TRƯỚC — chỉ xem, không đá người đang điều khiển. Không ai
#                       điều khiển → máy PC phát 1 luồng nhỏ (480p, 8 khung/giây, ~350 kbps); đang có người điều khiển → ô chỉ nhận khung khoá thưa.
#                       Máy PC KHÔNG cần cập nhật. Phát hình (bluestream) bật lại ~10 giây. Tắt ô xem trước máy PC: PC_PREVIEW=0 trong cloudphone.conf
#        22/11a — 🌐 PROXY RIÊNG TỪNG CLOUD PHONE: khách dán IP:Port:User:Pass (web / app) → cpapi (bản 22/11a, chỉ chủ máy) → phonectl
#                       proxy → cbproxy (Go, chạy root TRONG máy Android: iptables bắt TCP của app → proxy SOCKS5 / HTTP của khách).
#                       Proxy chết / sai mật khẩu → máy tự đi mạng thường. phonectl tự tải windows/cbproxy-x86_64 (md5 ghim) lần đầu dùng.
#                       Bật lại tự động: máy bật / khởi động lại / vòng 5 phút. Máy PC (VPS GPU) KHÔNG đụng. Xem: python phonectl.py proxy TÊN --get
#        21/11a — TRẠM TRUNG CHUYỂN MÁY PC CHO THUÊ (đợt 2 của "Máy PC"): thêm file pcrelay.py cạnh bluestream.py. Máy PC thuê tự nối RA cổng
#                       phát hình của máy chủ này rồi chờ; khách mở điều khiển máy PC trên web / app cũng nối vào đây → máy chủ ghép 2 kết nối
#                       (hình máy PC → khách, chuột phím khách → máy PC; máy chủ KHÔNG giải mã hình). Phần máy điện thoại KHÔNG đổi.
#                       Cần SQL v43 trên web. Tắt trạm trên 1 máy chủ: `python phonectl.py setconf PC_RELAY=0` rồi chạy lại lệnh này.
#        19/11a — BỘ NHỚ MÁY KHÁCH THEO CẤU HÌNH + KHÁCH MUA THÊM: máy khách MuMu chỉ có 2,9GB (máy mẫu tạo ở "chế độ ổ nhỏ" → máy nhân
#                       bản cũng vậy). phonectl: máy TẠO TỪ BẢN NÀY lúc lên lần đầu tự nới /data (ngay lúc máy chạy, giữ dữ liệu, ~1 giây)
#                       theo RAM: dưới 4GB → 8GB · 4–7GB → 13GB · từ 8GB → 16GB (web chạy SQL v40 thì web quyết định cỡ). Khách MUA THÊM
#                       bộ nhớ trên web (admin bật + đặt giá) → cloudphoned gọi `phonectl disk TÊN --gb N` → nới ngay, không tắt máy;
#                       máy đang ngủ thì nới lúc bật; nới không được → tự hoàn tiền. MÁY CŨ ĐỂ NGUYÊN (chủ máy chọn) trừ khi khách mua.
#                       Xem: `python phonectl.py bonho` · nới 1 máy cũ: `python phonectl.py bonho --sua TÊN` · tắt: setconf DISK_FIX=0
#        18/11a — MÁY KHÁCH CHỈ TỰ NGỦ KHI BỎ KHÔNG 18 GIỜ (trước: 30 phút — khách treo máy kêu "máy cứ tự nghỉ"). phonectl chỉ cho ngủ khi
#                       18 giờ liền không ai mở máy + không thấy máy có việc (game / app ở màn trước, app chạy nền) + 30 phút gần nhất máy
#                       đứng yên. Máy treo game KHÔNG bao giờ bị tắt. Đổi số giờ: IDLE_STOP_H trong cloudphone.conf · tắt hẳn: IDLE_STOP_MIN=0
#        17/11h — TỰ TẮT TIẾNG WINDOWS CỦA MÁY CHỦ (máy khách phát tiếng game ra loa máy chủ; khách không nghe tiếng từ máy chủ nên không
#                       ảnh hưởng): lệnh này tắt ngay, phonectl (chống kẹt) kiểm 10 phút / lần — chỉ bật nút mute của loa Windows, KHÔNG
#                       đụng giả lập. Thôi tự tắt: `python phonectl.py setconf HOST_MUTE=0` · bật tiếng lại: `python phonectl.py tattieng --bat`
#        17/11g — MÁY CHỦ BỊ TẮT NGANG (mất điện / bấm reset / sập) LÀM HỎNG FILE HỆ THỐNG ANDROID của máy khách đang chạy (roles.xml rỗng…)
#                       → Android sập liên tục, không bao giờ lên, khách "thức dậy… quay mãi". phonectl: tự đổi tên file hỏng (Android tự
#                       tạo lại, GIỮ dữ liệu khách) ở mọi chỗ chờ máy lên — khách mở máy, đợt bật sau khi máy chủ khởi động lại, chống kẹt,
#                       lệnh ksfix; lệnh mới `phonectl.py khammay TÊN` (chỉ đọc): nói VÌ SAO máy không lên. bluestream: máy lên lâu thì báo
#                       thật cho khách; bật lỗi → tự khám máy ghi nhật ký. Lệnh này: máy sửa rồi vẫn không lên → in kết quả khám máy
#                       (KHÔNG còn gợi ý xoá máy), báo số lần máy chủ bị tắt ngang 3 ngày qua, báo khách mở máy ngủ lên trong bao lâu.
#        17/11f — MÁY CHỦ KHỞI ĐỘNG LẠI: phonectl bật máy khách SONG SONG (máy 72 luồng: 4 máy cùng lúc; trước: từng máy một, mỗi máy chờ
#                       tới 5 phút), máy có khách vừa dùng lên trước, khách mở máy nào máy đó được chen lên, máy ảo treo lúc bật tự tắt
#                       hẳn + bật lại 1 lần · KHÔNG MẤT DỮ LIỆU: khởi động lại máy chủ bằng nút trên web / lệnh `phonectl.py rebootserver`
#                       / `phonectl.py tatem` → Android tự ghi dữ liệu rồi tắt (trước: tắt ngang); bấm Restart bằng tay → bảng kịp bảo mọi
#                       máy ghi dữ liệu xuống đĩa · MÁY ĐÃ HUỶ: cloudphoned tự dọn ~1 phút sau khi bật rồi 10 phút / lần (trước 30 phút),
#                       dọn cả máy MẤT TÊN ("Android Device-N") của khách đã huỷ; lệnh A dọn ngay · HÌNH VỠ: bluestream không bao giờ gửi
#                       khung thiếu lát, không học sai cách chia lát (lỗi làm hình vỡ mãi), nhớ cách chia qua lần bật lại bộ nén
#        17/11e — bluestream: DÁN CHỮ VÀO TERMUX (Termux bỏ qua phím PASTE → khách bấm "Dán chữ" mà Termux đứng im → nay dán bằng
#                       Ctrl+Alt+V của Termux) · HẾT KẸT HÌNH VỠ Ô SAU KHI MẠNG YẾU (mức mạng yếu nhớ từ lâu không còn kéo phiên mới xuống
#                       272x480; khách tự chọn chất lượng → dò lại từ đầu; yên 3 phút → bỏ trần cũ) · ghép lát chờ thêm khi còn thiếu lát
#        17/11a — MÁY CHỦ LDPLAYER (Android 9): khách mở máy chỉ thấy OFFLINE (máy chủ quay cửa sổ LDPlayer, Windows đóng phiên quay
#                       ngay) → bluestream: máy chủ LDPlayer mặc định lấy hình thẳng từ Android, phiên quay bị đóng thì tự chuyển ·
#                       lệnh này tự ghi CAPTURE=scrcpy · LDPlayer vừa cài chưa có máy nào ("không đọc được danh sách máy") →
#                       phonectl tự tạo máy gốc 'LDPlayer' rồi tạo máy khách · --kiemhinh không kết luận bừa khi máy chưa lên
#        phonectl     — 16/11k2: máy hỏng sổ khoá KHỞI ĐỘNG LẠI LIÊN TỤC (không bao giờ "lên", adb chập chờn) → canh + sửa ở mọi chỗ
#                       chờ máy lên, chống kẹt, lệnh ksfix canh tới khi nối được · trước khi tắt máy ảo: Android ghi hết dữ liệu xuống đĩa
#                       16/11k: SỔ KHOÁ ANDROID HỎNG (máy mới / máy đang chạy sập liên tục, màn đen, khách chờ hàng giờ) → tự
#                       sửa lúc máy lên + lệnh ksfix · đặt ảnh nền xong chờ giao diện lên thật mới giao máy
#                       16/11e: KHỞI ĐỘNG LẠI KHÔNG KẸT: xin lượt bật khi máy còn chạy rồi mới tắt (máy không nằm tắt chờ lượt) · lệnh
#                       tạo máy (nhân bản) nhường máy đang khởi động lại bật trước · chống kẹt: máy chủ bận thì để lần sau, không tắt
#                       máy rồi chờ CPU dịu · dấu "đang khởi động lại" ghi lúc tắt thật, kèm giờ chạy (không nhầm số PID cũ)
#        bluestream   — 16/11k: HẾT HÌNH VỠ / NHIỄU MÀU khi đổi FPS (cỡ hình chia hết 16, ghép đủ lát mỗi khung, dọn bộ nén cũ) ·
#                       chẩn đoán: python bluestream.py --kiemhinh TÊN_MÁY
#                       16/11e: nhận đúng lệnh khởi động lại còn chạy · quá 3 phút báo thật "máy chủ đang bận" · app PC không bị bảo
#                       bấm khởi động lại lần nữa khi máy đang khởi động lại
#        cpapi        — 16/11e: lệnh khởi động lại / đổi FPS / root / chế độ vẽ được chờ tới 40 phút (trước 2 phút → bị cắt giữa chừng,
#                       máy nằm tắt, khách thấy "Không khởi động lại được … timed out")
#        cloudphoned  — 16/11h: máy chủ đang "Ngừng nhận máy" → giữ đơn admin tạo máy thử ở đó (không chuyển đi)
#                       16/11g: máy chủ tạo máy mà máy không lên → tự ngừng nhận đơn 20 phút + báo admin
#                       16/11f: đơn tạo máy quá 30 phút chưa lên → tự huỷ + hoàn tiền, báo khách tạo máy mới (SQL v36) · đơn đã
#                       huỷ không "sống lại" (máy tạo dở tự xoá) · máy chủ đang quá tải tạo máy → tạm nhường đơn mới cho máy chủ khác
#                       16/11e: đơn ADMIN chọn máy chủ GẦN ĐẦY (≥ 80%) → tự chuyển sang máy chủ còn trống nhất
#        cloudphoned  — 16/11d: TRẦN 100 NHÂN mỗi máy chủ (trước 68) · đơn mới ƯU TIÊN máy chủ còn trống (tính cả nhân đã cấp) · tạo máy
#                       mà máy chủ hết chỗ → TRẢ ĐƠN cho máy chủ khác còn chỗ (không hoàn tiền nhầm), máy chủ đó nghỉ nhận đơn 5 phút
#        bluestream   — 16/11c: HÌNH SẠCH KHI LƯỚT (khung khoá 2 giây, bộ đệm lớn hơn, nén đẹp hơn, mạng yếu thì bớt điểm ảnh thay vì vỡ ô)
#                       · máy đang KHỞI ĐỘNG LẠI → khách mở máy được báo "đang khởi động lại, tự vào khi máy lên" (không báo lỗi)
#        phonectl     — 16/11c: ghi dấu "máy đang khởi động lại" cho phát hình biết
#        bluestream   — 16/11a: hết quay mãi "Máy chủ chưa bật được hình" (máy tắt / Android chưa lên → tự gọi bật máy đang TẮT, báo
#                       khách rõ + nút Khởi động lại máy) · MẠNG YẾU vẫn mượt (khung khoá theo giây thật, đo sức đường truyền để hạ
#                       đúng mức ngay, nhớ trần, bắt đầu nhẹ theo gợi ý của app)
#        phonectl     — 16/11: KHÁCH TỰ ĐỔI FPS (bật máy là ghi FPS khách chọn) · khách bấm Khởi động lại mà máy treo → tắt hẳn đúng
#                       máy đó rồi bật · wake báo WAKE_RUNNING và KHÔNG bật chen ngang lệnh khác đang làm dở với máy đó
#        phonectl     — 15/11: ĐỔI ANDROID lỗi "chưa tạo được máy mới": MuMu báo "mainnx request failed" lúc nhân bản máy mẫu →
#                       tự mở lại chương trình chính MuMu rồi nhân bản lại (trước chỉ bật / tắt máy mới tự mở lại); tin báo lỗi ghi rõ LÝ DO
#        cloudphoned  — tự sửa an toàn hơn (không tắt phát hình chỉ vì máy chủ chậm trả lời, bớt tin Telegram rác),
#                       máy mới / đổi Android chưa lên thì CHƯA giao cho khách (hết cảnh mở ra màn đen)
#        bluestream   — 13/11c: khách mở máy → bật sáng màn hình Android trước khi lấy hình
#        panel        — mở bảng CloudBlue kiểu nào cũng tự bật A→Z (dịch vụ + máy khách) nếu chưa chạy gì
#        cloudphoned  — TRẦN CỨNG mỗi máy chủ: cấp tới 68 nhân / 112GB là ngừng nhận (không bán vượt); hết hạn / huỷ / đổi Android
#                       xoá hẳn máy + dữ liệu, máy sót tự dọn 30 phút / lần
#        phonectl     — GIÃN CÁCH BẬT MÁY: tối đa 2 máy cùng khởi động (khách đang chờ được 3), cách nhau 20 giây
#        17/11e — phonectl: GIẢ LẬP CHẠY LẪN QUYỀN ADMIN (lệnh A dán vào PowerShell thường → máy bật từ đó chạy quyền thường, bảng chạy
#                       Admin → MuMu "Unable to start the Android Device … administrator privileges", không bật được máy nào) → không
#                       bật máy từ cửa sổ khác quyền + lệnh `quyen --sua` bật lại đúng máy chạy sai quyền. Lệnh A: phải chạy CÙNG quyền
#                       với bảng (thường là Admin), khác quyền thì dừng ngay từ đầu, không đụng gì
#        24/11a — phonectl: MuMu tạo máy mẫu ĐÚNG bản Android bằng lệnh (create --version 12/15 --mini; trước đây tạo mới luôn ra
#                       Android 15 → không tạo được tpl_a12) · lệnh A: máy chủ MuMu còn thiếu máy mẫu tpl_a12 / tpl_a15 → TỰ TẠO (tự đặt
#                       tên, để TẮT) · cloudphoned báo tên máy Windows (web nối máy chủ với điều khiển từ xa)
#        24/11b — BẢN MỚI TỰ CÀI, không cần bấm: GitHub có bản mới chưa máy chủ nào chạy → máy chủ ÍT KHÁCH NHẤT tự cài thử trước
#                       (hỏi GitHub 15 phút / lần), chạy ổn đủ thời gian chờ (web: 🛠 Quản lý, mặc định 20 phút) → các máy chủ khác tự
#                       theo · vừa tạo máy mẫu → cloudphoned đọc lại NGAY, web bán thêm bản Android đó sau ≤ 30 giây (trước: tới 10 phút)
#   2. Bật lại đúng dịch vụ vừa thay / đang chạy bản cũ (bảng CloudBlue tự bật lại sau 5 giây) — không đụng máy khách
#   3. Tự chạy khi Windows khởi động lại: tác vụ / lối tắt phải có --auto · bảng mở mà chưa chạy gì → mở lại bảng kiểu tự bật
#   4. Kiểm cổng phát hình, đường hầm Cloudflare
#   5. Kiểm từng máy khách: nối adb, Android đã lên chưa, bật sáng màn hình, màn đen
#   6. Máy chưa lên / mất adb / đen ở màn hình chính → ép khởi động lại. Máy đen mà đang mở app/game → KHÔNG đụng, chỉ báo
#      (game treo máy hay tắt hình cho nhẹ). Máy khách tắt ngoài ý muốn → bật lại.
#   Chạy:  python sua-tat-ca.py            · chỉ kiểm, không thay / không bật lại gì:  python sua-tat-ca.py --chi-kiem
#          tự cập nhật (cloudphoned / web admin gọi — không có người xem, không đụng máy khách):  python sua-tat-ca.py --tu-dong
import ast, concurrent.futures as cf, datetime, json, os, re, struct, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception: pass

VER = "27/11g"
B = os.environ.get("CB_HOME") or os.path.dirname(os.path.abspath(__file__))
ADB = os.path.join(B, "platform-tools", "adb.exe")
PHONECTL = os.path.join(B, "phonectl.py")
LOGS = os.path.join(B, "logs")
REPO = "lvhien205hn-eng/cloudblue"
NW = 0x08000000 if os.name == "nt" else 0
ONLY_CHECK = "--chi-kiem" in sys.argv
REMAKE = "--lam-moi-may-ma" in sys.argv          # tạo lại máy MỚI cho khách có máy "ma" (web còn thuê, máy chủ mất hẳn máy)
REMAKE_BROKEN = "--lam-moi-may-hong" in sys.argv  # máy ép khởi động lại rồi vẫn KHÔNG lên → xoá máy hỏng + tạo lại máy mới (mất dữ liệu)
NO_UPDATE = ONLY_CHECK or "--khong-cap-nhat" in sys.argv
AUTO = "--tu-dong" in sys.argv                    # 23/11f: máy chủ TỰ chạy (web admin bấm Cập nhật / cloudphoned tự theo máy chủ khác) — không có
                                                  # người xem: chỉ thay bản mới + bật lại dịch vụ + kiểm tự chạy / mạng, KHÔNG kiểm / sửa máy khách
STATE_F = os.path.join(LOGS, "cap-nhat.json")     # 23/11f: kết quả lần cập nhật gần nhất — cloudphoned báo lên web (thẻ máy chủ), máy chủ khác nhìn để tự theo
RUN = {"changed": [], "p_upd": [], "p_rst": [], "probs": [], "done": False}
ENV = dict(os.environ, PATH=os.path.join(B, "platform-tools") + os.pathsep + os.environ.get("PATH", ""), PYTHONIOENCODING="utf-8",
           PYTHONUTF8="1", ADB_LOCAL_TRANSPORT_MAX_PORT="5553")
# (đường dẫn trên GitHub, tên file trên máy chủ, dấu chắc chắn của bản mới, dịch vụ)
FILES = [("cloudphoned.py", "cloudphoned.py", "cloudphoned bản 27/11b", "cloudphoned"),
         ("windows/bluestream.py", "bluestream.py", 'BS_SUB = "27/11g"', "bluestream"),
         ("windows/pcrelay.py", "pcrelay.py", 'PCRELAY_VER = "22/11b"', "bluestream"),      # file MỚI của bluestream (trạm máy PC) — xem NEW_WITH
         ("windows/panel.py", "panel.py", "def on_winoff", "panel"),
         ("windows/phonectl.py", "phonectl.py", 'PCTL_SUB = "27/11e"', None),
         ("cpapi.py", "cpapi.py", "cpapi bản 23/11f", "cpapi")]
NEW_WITH = {"pcrelay.py": "bluestream.py"}       # file mới chưa từng có trên máy chủ: vẫn cài nếu máy chủ có file đi cùng (pcrelay.py là 1 phần của bluestream.py)
MARK_RUN = {"cloudphoned": "cloudphoned bản 27/11b", "bluestream": "bản 27/11g: Android 9 cbvideo", "cpapi": "cpapi bản 23/11f"}   # dòng khởi động của bản mới (trong nhật ký)
SVC_RX = {"cloudphoned": r"cloudphoned\.py\W*$", "bluestream": r"bluestream\.py\W*$", "cpapi": r"cpapi\.py\W*$"}
SVC_LOG = {"cloudphoned": "cloudphoned.log", "bluestream": "phat-hinh.log", "cpapi": "cpapi.log"}
SVC_VN = {"cloudphoned": "nhận đơn (cloudphoned)", "bluestream": "phát hình (bluestream)", "cpapi": "công cụ máy (cpapi)"}
SVC_FILE = {"cloudphoned": "cloudphoned.py", "bluestream": "bluestream.py", "cpapi": "cpapi.py"}
CYCLE_RX = r"phonectl\.py\S*\s+(?:restart|reconfig|resize|render|rootcfg|ramfix|rootfix(?!\s+--all))\s"   # khách đang khởi động lại / đổi cấu hình máy
HOME_PK = ("launcher", "lawnchair", "systemui", "keyguard", "trebuchet", "quickstep", "nexuslauncher", "com.android.settings")

def say(*a): print(*a, flush=True)

def run(cmd, t=30, raw=False):
    """Chạy 1 lệnh → chữ (hoặc byte). Không bao giờ ném lỗi; quá giờ → '' (chương trình bị tắt)."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=t, creationflags=NW, env=ENV, stdin=subprocess.DEVNULL)
        return r.stdout if raw else (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return b"" if raw else ""

def run2(cmd, t=30):
    """(mã thoát, stdout + stderr) — mã -1 = quá giờ / không chạy được."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=t, creationflags=NW, env=ENV, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)

def ps(script, t=90):
    return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], t)

def adb(*a, t=15, raw=False): return run([ADB] + [str(x) for x in a], t, raw)

def pctl(*a, t=600): return run2([sys.executable, PHONECTL] + [str(x) for x in a], t)

def tail(path, nb=2000000):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2); z = fh.tell(); fh.seek(max(0, z - nb)); return fh.read().decode("utf-8", "replace").splitlines()
    except Exception:
        return []

def conf():
    c = {}
    for ln in tail(os.path.join(B, "cloudphone.conf"), 300000):
        ln = ln.lstrip("﻿")
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1); c[k.strip()] = v.strip()
    return c

def listening(ports):
    out = run(["netstat", "-ano"], 40)
    if not out.strip(): return None
    return {p for p in ports if re.search(r":%d\s+(?:0\.0\.0\.0|\[::\]|127\.0\.0\.1):0\s" % int(p), out)}

def procs(rx):
    """[(pid, số giây đã chạy)] các chương trình python* có dòng lệnh khớp rx."""
    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match '%s' } | "
             "ForEach-Object { '{0} {1}' -f $_.ProcessId, [int]((Get-Date) - $_.CreationDate).TotalSeconds }" % rx.replace("'", "''"), 60)
    res = []
    for ln in out.splitlines():
        q = ln.split()
        if len(q) == 2 and q[0].isdigit() and q[1].lstrip("-").isdigit() and int(q[0]) != os.getpid(): res.append((int(q[0]), int(q[1])))
    return res

def py_cmdlines():
    return ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | ForEach-Object { $_.CommandLine }", 60)

def kill(pid): return run(["taskkill", "/PID", str(pid), "/F"], 30)       # CHỈ tắt đúng chương trình đó (không /T: giữ giả lập / adb)

# ------------------------------------------------------------------ 0. sổ ghi lần cập nhật (23/11f)
def state_read():
    try:
        d = json.load(open(STATE_F, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def state_write(d):
    try:
        os.makedirs(LOGS, exist_ok=True)
        with open(STATE_F + ".tmp", "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False)
        os.replace(STATE_F + ".tmp", STATE_F)
    except Exception:
        pass

def pid_alive(pid):
    try: return str(int(pid)) in run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], 30)
    except Exception: return False

def state_begin():
    """Ghi "đang cập nhật". Trả False khi lần chạy TỰ ĐỘNG này phải thôi vì đang có lần cập nhật khác chạy dở (dưới 30 phút, tiến trình còn sống)."""
    if NO_UPDATE: return True
    st = state_read(); r = st.get("running") or {}
    if AUTO and r.get("pid") and r.get("pid") != os.getpid() and time.time() - float(r.get("start") or 0) < 1800 and pid_alive(r["pid"]): return False
    st["running"] = {"ver": VER, "start": int(time.time()), "auto": AUTO, "pid": os.getpid()}
    state_write(st); return True

def files_new():
    """{tên file: đã là bản mới (có dấu của bản này)} cho các file máy chủ này có."""
    res = {}
    for gp, local, mark, svc in FILES:
        lp = os.path.join(B, local)
        if not os.path.isfile(lp): continue
        try: res[local] = mark.encode("utf-8") in open(lp, "rb").read()
        except OSError: res[local] = False
    return res

def state_end():
    """Ghi kết quả. upd = phần CẬP NHẬT xong sạch (mọi file là bản mới + dịch vụ đã chạy bản mới). Sổ giữ:
       ver / at = bản máy chủ này đang chạy + lúc cài xong bản đó (chạy lại lệnh A cùng bản KHÔNG đổi "at" — máy chủ khác tính thời gian chạy ổn
       từ đó) · last = lượt gần nhất (kể cả lượt hỏng) · ok = lượt gần nhất không còn dòng ✗ nào."""
    if NO_UPDATE: return
    fn = files_new(); now = int(time.time())
    upd = bool(RUN["done"]) and not RUN["p_upd"] and not RUN["p_rst"] and bool(fn) and all(fn.values())
    d = state_read(); d.pop("running", None)
    if upd:
        if d.get("ver") != VER or not d.get("upd") or not d.get("at"): d["at"] = now
        d["ver"], d["upd"] = VER, True
    d.update(ok=bool(RUN["done"]) and not RUN["probs"], auto=AUTO, changed=sorted(set(RUN["changed"])), probs=[str(x)[:200] for x in RUN["probs"]][:8],
             files=fn, last={"ver": VER, "at": now, "upd": upd, "auto": AUTO})
    state_write(d)

# ------------------------------------------------------------------ 1. cập nhật file
def gh_get(path):
    """Tải 1 file từ GitHub (nhánh main): API (không bị bộ đệm) → raw → curl.exe. None = không tải được."""
    tries = [("https://api.github.com/repos/%s/contents/%s?ref=main" % (REPO, path), {"Accept": "application/vnd.github.raw"}),
             ("https://raw.githubusercontent.com/%s/main/%s?t=%d" % (REPO, path, int(time.time())), {})]
    for url, h in tries:
        try:
            req = urllib.request.Request(url, headers=dict({"User-Agent": "cloudblue-sua-tat-ca", "Cache-Control": "no-cache"}, **h))
            with urllib.request.urlopen(req, timeout=60) as r: data = r.read()
            if len(data) > 2000: return data
        except Exception:
            pass
    for url, h in tries:                                   # Python không tải được (chứng chỉ cũ…) → curl.exe của Windows
        tmp = os.path.join(B, "redroid", "sua-tai.tmp")
        try:
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            run(["curl.exe", "-sSL", "-H", "User-Agent: cloudblue-sua-tat-ca"] + (["-H", "Accept: " + h["Accept"]] if h else []) + ["-o", tmp, url], 120)
            data = open(tmp, "rb").read(); os.remove(tmp)
            if len(data) > 2000: return data
        except Exception:
            pass
    return None

def good_py(data, name):
    try: ast.parse(data.decode("utf-8"), name); return True
    except Exception: return False

CREATE_RX = r"phonectl\.py\S*\s+(create|resize)\s"
HUNG_S = 1800                                      # lệnh tạo / nâng máy chạy quá 30 phút = treo (bình thường 2–6 phút)
def wait_not_creating(limit=600):
    """Đang tạo / nâng cấp máy khách → chờ xong rồi mới bật lại nhận đơn (tối đa 10 phút). Lệnh tạo đã chạy quá 30 phút = TREO
       → tắt riêng lệnh đó (đơn đó được hoàn tiền / tạo lại) rồi đi tiếp. True = không còn lệnh tạo nào."""
    t0 = time.time(); said = 0
    while True:
        pr = procs(CREATE_RX)
        if not pr: return True
        hung = [pid for pid, age in pr if age > HUNG_S]
        if hung:
            for pid in hung: kill(pid)
            say(f"   ⚠ lệnh tạo / nâng máy chạy quá {HUNG_S // 60} phút (treo) → đã tắt riêng lệnh đó (pid {', '.join(map(str, hung))})")
            continue
        if time.time() - t0 >= limit: return False
        if time.time() - said > 60: say("   … đang tạo / nâng cấp máy khách — chờ xong rồi mới bật lại nhận đơn (tối đa 10 phút)"); said = time.time()
        time.sleep(10)

def wait_no_cycles(limit=300):
    """16/11e: cpapi đang chạy lệnh khởi động lại / đổi cấu hình cho khách → chờ xong rồi mới bật lại cpapi (tối đa 5 phút).
       Bật lại cpapi lúc đó: máy vẫn khởi động lại bình thường nhưng app / web của khách mất theo dõi việc đang làm."""
    t0 = time.time(); said = 0
    while procs(CYCLE_RX):
        if time.time() - t0 >= limit: return False
        if time.time() - said > 60: say("   … khách đang khởi động lại / đổi cấu hình máy — chờ xong rồi mới bật lại công cụ máy (tối đa 5 phút)"); said = time.time()
        time.sleep(10)
    return True

def update_files():
    changed = []; problems = []
    say("1/6 Cập nhật bản sửa từ GitHub")
    if NO_UPDATE: say("   (bỏ qua — chỉ kiểm)"); return changed, problems
    todo = []
    for gp, local, mark, svc in FILES:
        lp = os.path.join(B, local)
        if not os.path.isfile(lp) and svc != "panel" and not (local in NEW_WITH and os.path.isfile(os.path.join(B, NEW_WITH[local]))):
            say(f"   - {local}: máy chủ này không có — bỏ qua"); continue
        data = gh_get(gp)
        if data is None: say(f"   ✗ {local}: không tải được từ GitHub (mạng?) — giữ bản đang có"); problems.append(f"không tải được {local}"); continue
        if mark.encode("utf-8") not in data:
            say(f"   ✗ {local}: GitHub CHƯA có bản mới ({mark}) — tải đủ file lên GitHub rồi chạy lại lệnh"); problems.append(f"GitHub chưa có {local} mới"); continue
        if not good_py(data, local): say(f"   ✗ {local}: file tải về bị lỗi — giữ bản đang có"); problems.append(f"{local} tải về lỗi"); continue
        try: cur = open(lp, "rb").read()
        except OSError: cur = b""
        if cur == data: say(f"   = {local}: đã là bản mới"); continue
        todo.append((local, lp, data, svc))
    for local, lp, data, svc in todo:
        try:
            bak = lp + ".truoc-2111a"
            if os.path.isfile(lp) and not os.path.isfile(bak):
                with open(lp, "rb") as a, open(bak, "wb") as b: b.write(a.read())
            with open(lp + ".new", "wb") as f: f.write(data)
            os.replace(lp + ".new", lp)
            say(f"   ✓ {local}: " + ("đã thay bản mới (bản cũ: " + os.path.basename(bak) + ")" if os.path.isfile(bak) else "đã thêm file mới" if local in NEW_WITH else "đã thay bản mới"))
            changed.append(svc or local)
        except Exception as e:
            say(f"   ✗ {local}: không ghi được ({e}) — đóng chương trình đang mở file này rồi chạy lại"); problems.append(f"không ghi được {local}")
    return changed, problems

# ------------------------------------------------------------------ 1b. máy chủ LDPlayer (17/11a)
def ld_fix(c, changed):
    """Máy chủ LDPlayer (Android 9): (1) hình phải lấy THẲNG từ Android — quay cửa sổ LDPlayer thì khách mở máy chỉ thấy OFFLINE (Windows
       đóng phiên quay ngay, win8 17/11) hoặc thấy quảng cáo LDPlayer (win1 13/11) → ghi CAPTURE=scrcpy + bật lại phát hình;
       (2) LDPlayer phải có ít nhất 1 máy (máy gốc) thì mới tạo được máy khách → chưa có thì tạo. Máy chủ MuMu / MEmu: không làm gì.
       --chi-kiem: chỉ báo. Trả [dòng cho phần TÓM TẮT]."""
    probs = []
    e = (c.get("EMU") or "").strip().lower()
    if e in ("mumu", "memu"): return probs
    if e != "ld":                                            # cấu hình cũ không ghi EMU → hỏi phonectl (chỉ đọc)
        rc, out = pctl("engine", t=120)
        try: e = str(json.loads((out or "").strip().splitlines()[-1]).get("emu") or "") if rc == 0 else ""
        except Exception: e = ""
        if e != "ld": return probs
    cap = (c.get("CAPTURE") or "").strip().lower()
    if cap == "scrcpy": say("   ✓ máy chủ LDPlayer: hình lấy thẳng từ Android (CAPTURE=scrcpy)")
    elif cap in ("wgc", "gdi"):
        say(f"   ⚠ máy chủ LDPlayer đang ÉP quay cửa sổ (CAPTURE={cap}) — khách có thể thấy quảng cáo LDPlayer / mở máy báo OFFLINE.\n"
            "     Bỏ ép: python phonectl.py setconf CAPTURE=scrcpy  rồi chạy lại lệnh này")
    elif ONLY_CHECK:
        say("   ✗ máy chủ LDPlayer CHƯA ghi CAPTURE=scrcpy (đang quay cửa sổ → khách mở máy có thể chỉ thấy OFFLINE)"); probs.append("máy chủ LDPlayer chưa ghi CAPTURE=scrcpy")
    else:
        pctl("setconf", "CAPTURE=scrcpy", t=60)
        if (conf().get("CAPTURE") or "").strip().lower() == "scrcpy":
            say("   ✓ máy chủ LDPlayer: đã ghi CAPTURE=scrcpy → hình lấy thẳng từ Android (trước: quay cửa sổ LDPlayer → khách mở máy báo OFFLINE / thấy quảng cáo)")
            if "bluestream" not in changed: changed.append("bluestream")          # bật lại phát hình để dùng cách lấy hình mới
        else:
            say("   ✗ máy chủ LDPlayer: chưa ghi được CAPTURE=scrcpy vào cloudphone.conf"); probs.append("chưa ghi được CAPTURE=scrcpy (máy chủ LDPlayer)")
    if ONLY_CHECK:
        rc, out = pctl("vmlist", t=120)
        if rc == 0 and not [ln for ln in (out or "").splitlines() if re.match(r"^\d+,", ln.strip())]:
            say("   ✗ LDPlayer chưa có máy nào (chưa có máy gốc) → chưa tạo được máy khách"); probs.append("LDPlayer chưa có máy gốc — chạy lệnh A không kèm --chi-kiem")
        return probs
    rc, out = pctl("ldbase", t=300)
    last = next((ln.strip() for ln in reversed((out or "").splitlines()) if ln.strip().startswith("LDBASE")), "")
    if last.startswith("LDBASE da_tao"): say("   ✓ LDPlayer chưa có máy nào → đã tạo máy gốc 'LDPlayer' (để nguyên, đừng xoá) — giờ tạo được máy khách")
    elif last.startswith("LDBASE loi"):
        say("   ✗ LDPlayer không đọc được danh sách máy (" + last[10:].strip()[:120] + ") → mở LDPlayer 1 lần, thấy có máy trong danh sách rồi chạy lại lệnh")
        probs.append("LDPlayer không đọc được danh sách máy — mở LDPlayer 1 lần rồi chạy lại lệnh A")
    return probs

# ------------------------------------------------------------------ 1c. máy chủ MuMu: máy mẫu (24/11a)
MUMU_TPL_VERS = ("12", "15")                             # bản Android MuMu tạo được bằng lệnh (create --version)
ENG_POKE_F = os.path.join(LOGS, "doc-lai-may-mau.txt")  # 24/11b: cloudphoned thấy file này mới hơn lần đọc trước → đọc lại máy mẫu ngay
def eng_poke():
    try:
        os.makedirs(LOGS, exist_ok=True)
        with open(ENG_POKE_F, "w", encoding="utf-8") as f: f.write(str(int(time.time())))
    except Exception: pass
def mumu_tpl(c):
    """Máy chủ MuMu phải có máy MẪU cho mỗi bản Android bán (tpl_a12 = Android 12, tpl_a15 = Android 15): máy khách nhân bản từ đó.
       Thiếu → TỰ TẠO bằng phonectl mktpl (MuMu: create --version N --mini, tự đặt tên, để TẮT) — khỏi mở MuMu bấm tay.
       Đọc danh sách máy lỗi → không tạo gì (không tạo trùng). --chi-kiem: chỉ báo. Máy chủ LDPlayer / MEmu: không làm gì.
       Trả [dòng cho phần TÓM TẮT]."""
    probs = []
    if (c.get("EMU") or "").strip().lower() != "mumu": return probs
    want = [v.strip() for v in (c.get("ANDROIDS") or "12,15").split(",") if v.strip() in MUMU_TPL_VERS]
    if not want: return probs
    rc, out = pctl("vmlist", t=180)
    names = {ln.split(",")[1].strip() for ln in (out or "").splitlines() if re.match(r"^\d+,[^,]+,", ln.strip())}
    if rc != 0 or not names:
        say("   (máy mẫu MuMu: chưa đọc được danh sách máy — lần sau kiểm lại)"); return probs
    miss = [v for v in want if f"tpl_a{v}" not in names]
    if not miss:
        say("   ✓ máy mẫu MuMu đủ: " + ", ".join(f"tpl_a{v}" for v in want)); return probs
    if ONLY_CHECK:
        say("   ✗ máy chủ MuMu THIẾU máy mẫu " + ", ".join(f"tpl_a{v}" for v in miss) + " → web không bán bản đó ở máy chủ này (chạy lệnh A không kèm --chi-kiem để tự tạo)")
        return [f"thiếu máy mẫu " + ", ".join(f"tpl_a{v}" for v in miss)]
    say("   Máy chủ MuMu thiếu máy mẫu " + ", ".join(f"tpl_a{v} (Android {v})" for v in miss) + " → tự tạo bằng lệnh (mỗi máy 1–3 phút)…")
    rc, out = pctl("mktpl", ",".join(miss), t=1800)
    for ln in (out or "").splitlines():
        if ln.strip(): say("      " + ln.strip()[:300])
    eng_poke()                                           # 24/11b: cloudphoned đọc lại máy mẫu NGAY (không chờ tới 10 phút)
    rc2, out2 = pctl("vmlist", t=180)
    names2 = {ln.split(",")[1].strip() for ln in (out2 or "").splitlines() if re.match(r"^\d+,[^,]+,", ln.strip())}
    left = [v for v in miss if f"tpl_a{v}" not in names2] if names2 else miss
    if left:
        probs.append("chưa tạo được máy mẫu " + ", ".join(f"tpl_a{v}" for v in left)
                     + " — mở MuMu: + New → đúng bản Android → đổi tên tpl_aNN → để TẮT (2 phút sau web tự bán)")
    else:
        say("   ✓ đã tạo máy mẫu " + ", ".join(f"tpl_a{v}" for v in miss) + " — khoảng 30 giây nữa web tự bán thêm các bản này ở máy chủ này")
    return probs

# ------------------------------------------------------------------ 2. bật lại dịch vụ
def log_size(svc):
    try: return os.path.getsize(os.path.join(LOGS, SVC_LOG[svc]))
    except OSError: return 0

def log_new(svc, since):
    try:
        with open(os.path.join(LOGS, SVC_LOG[svc]), "rb") as fh:
            fh.seek(0, 2); z = fh.tell(); fh.seek(since if since <= z else 0); return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""

def restart_services(changed, done_new=()):
    say("2/6 Bật lại dịch vụ (bản mới chạy ngay)")
    probs = []
    if ONLY_CHECK: say("   (bỏ qua — chỉ kiểm)"); return probs
    waited = False
    for svc in ("cloudphoned", "bluestream", "cpapi"):
        fp = os.path.join(B, SVC_FILE[svc])
        if not os.path.isfile(fp): continue
        pr = procs(SVC_RX[svc])
        if not pr:
            say(f"   ⚠ {SVC_VN[svc]} đang KHÔNG chạy — bước 3 mở lại bảng CloudBlue"); continue
        try: age_file = time.time() - os.path.getmtime(fp)
        except OSError: age_file = 0
        old = svc in changed or any(age > age_file + 5 for _, age in pr)          # chạy từ TRƯỚC khi file được thay → đang chạy bản cũ
        if not old: say(f"   = {SVC_VN[svc]}: đang chạy đúng file hiện có" + (" (bản mới)" if svc in done_new else "")); continue
        if svc == "cloudphoned" and not waited:
            waited = True
            if not wait_not_creating():
                say("   ✗ nhận đơn: máy chủ đang tạo máy khách quá 10 phút — CHƯA bật lại (file mới đã thay), chạy lại lệnh sau ít phút")
                probs.append("nhận đơn chưa chạy bản mới (đang tạo máy) — chạy lại lệnh sau"); continue
        if svc == "cpapi" and not wait_no_cycles():
            say("   ✗ công cụ máy: khách đang khởi động lại máy quá 5 phút — CHƯA bật lại (file mới đã thay), chạy lại lệnh sau ít phút")
            probs.append("công cụ máy chưa chạy bản mới (khách đang khởi động lại máy) — chạy lại lệnh sau"); continue
        if svc == "bluestream": say("   … phát hình bật lại: khách đang xem bị ngắt ~10 giây rồi app tự nối lại")
        since = log_size(svc); t0 = time.time()
        for pid, _ in pr: kill(pid)
        say(f"   … {SVC_VN[svc]}: đã tắt bản cũ (pid {', '.join(str(p) for p, _ in pr)}) — chờ bảng CloudBlue bật lại bản mới")
        ok = False
        while time.time() - t0 < 90:
            time.sleep(3)
            if MARK_RUN[svc] in log_new(svc, since): ok = True; break
        newp = [p for p, _ in procs(SVC_RX[svc])]
        if ok:
            say(f"   ✓ {SVC_VN[svc]}: bản mới đã chạy sau {time.time() - t0:.0f} giây")
            if svc == "bluestream":                         # 21/11a: nói rõ trạm máy PC bật hay tắt (dòng khởi động của bluestream)
                ln = next((x for x in reversed(log_new(svc, since).splitlines()) if MARK_RUN[svc] in x), "")
                if " TẮT (" in ln: say("     ⚠ trạm máy PC cho thuê đang TẮT:" + ln.split(" TẮT", 1)[1][:160] + " — phần máy điện thoại vẫn chạy bình thường")
                elif " BẬT" in ln: say("     ✓ trạm máy PC cho thuê: BẬT (máy PC thuê nối vào cổng phát hình của máy chủ này)")
        elif newp: say(f"   ✓ {SVC_VN[svc]}: đã chạy lại (pid {newp[0]}) — chưa thấy dòng khởi động trong nhật ký, xem lại sau 1 phút")
        else:
            say(f"   ✗ {SVC_VN[svc]}: CHƯA chạy lại sau 90 giây → mở bảng CloudBlue bấm ▶ Bật tất cả"); probs.append(f"{SVC_VN[svc]} chưa chạy lại")
    return probs

# ------------------------------------------------------------------ 3. tự chạy khi Windows khởi động lại
AUTOSTART_PS = r"""
$t = Get-ScheduledTask -TaskName 'BlueRoblox' -ErrorAction SilentlyContinue
if ($t) { 'TASK=1'; 'TASK_ARG=' + $t.Actions[0].Arguments; 'TASK_RL=' + $t.Principal.RunLevel } else { 'TASK=0' }
$lnk = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\BlueRoblox.lnk"
if (Test-Path $lnk) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); 'LNK=1'; 'LNK_ARG=' + $s.Arguments } else { 'LNK=0' }
$u = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\CloudBlue.lnk"
if (Test-Path $u) { 'ULNK=1' } else { 'ULNK=0' }
$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -ErrorAction SilentlyContinue
'AUTOLOGON=' + $w.AutoAdminLogon
$a = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
'ADMIN=' + $a
"""
def kv(out):
    d = {}
    for ln in out.splitlines():
        if "=" in ln: k, v = ln.split("=", 1); d[k.strip()] = v.strip()
    return d

def pythonw():
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.isfile(w) else sys.executable

def fix_autostart():
    say("3/6 Tự chạy khi Windows khởi động lại")
    probs = []
    d = kv(ps(AUTOSTART_PS, 60))
    if not d: say("   ? không đọc được (PowerShell lỗi)"); return probs
    pw = pythonw(); pan = os.path.join(B, "panel.py")
    if d.get("TASK") == "1":
        rl = (d.get("TASK_RL") or "").strip().lower()                         # 17/11e2: bảng chạy quyền gì sau mỗi lần Windows lên
        if rl == "highest": say("   ✓ tác vụ BlueRoblox mở bảng bằng quyền Admin")
        elif rl:
            say("   ⚠ tác vụ BlueRoblox mở bảng bằng quyền THƯỜNG → lệnh A trên máy này phải chạy PowerShell thường.\n"
                "     Khuyên: bảng → 🔑 Tự đăng nhập + tự chạy (tác vụ chạy Admin) rồi khởi động lại Windows lúc vắng khách")
        if d.get("LNK") == "1" or d.get("ULNK") == "1":
            say("   ⚠ ngoài tác vụ còn lối tắt Startup cũng mở bảng (quyền thường) → mỗi lần Windows lên bảng có thể chạy khác quyền")
        if "--auto" in d.get("TASK_ARG", ""): say("   ✓ tác vụ BlueRoblox (tự mở bảng lúc đăng nhập): có --auto")
        elif ONLY_CHECK: say("   ✗ tác vụ BlueRoblox THIẾU --auto (bảng mở mà không tự bật gì)"); probs.append("tác vụ thiếu --auto")
        else:
            out = ps("$t = Get-ScheduledTask -TaskName 'BlueRoblox'; $a = $t.Actions[0]; $a.Arguments = ($a.Arguments + ' --auto').Trim(); "
                     "Set-ScheduledTask -TaskName 'BlueRoblox' -Action $a | Out-Null; (Get-ScheduledTask -TaskName 'BlueRoblox').Actions[0].Arguments", 60)
            if "--auto" in out: say("   ✓ tác vụ BlueRoblox thiếu --auto → đã thêm (lần sau Windows lên là tự bật A→Z)")
            else: say("   ✗ tác vụ BlueRoblox thiếu --auto mà không sửa được (mở PowerShell bằng quyền Admin rồi chạy lại)"); probs.append("tác vụ thiếu --auto")
    if d.get("LNK") == "1":
        if "--auto" in d.get("LNK_ARG", ""): say("   ✓ lối tắt Startup BlueRoblox: có --auto")
        elif not ONLY_CHECK:
            out = ps("$l = \"$env:ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\StartUp\\BlueRoblox.lnk\"; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l); "
                     "$s.TargetPath = '%s'; $s.Arguments = '\"%s\" --auto'; $s.WorkingDirectory = '%s'; $s.Save(); "
                     "(New-Object -ComObject WScript.Shell).CreateShortcut($l).Arguments" % (pw, pan, B), 60)
            if "--auto" in out: say("   ✓ lối tắt Startup BlueRoblox thiếu --auto → đã sửa")
            else: say("   ✗ lối tắt Startup thiếu --auto mà không sửa được (cần quyền Admin)"); probs.append("lối tắt thiếu --auto")
    if d.get("TASK") != "1" and d.get("LNK") != "1" and d.get("ULNK") != "1":
        if ONLY_CHECK: say("   ✗ CHƯA có gì tự mở bảng CloudBlue khi Windows lên"); probs.append("chưa tự chạy")
        else:
            out = ps("$l = \"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\CloudBlue.lnk\"; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l); "
                     "$s.TargetPath = '%s'; $s.Arguments = '\"%s\" --auto'; $s.WorkingDirectory = '%s'; $s.Save(); Test-Path $l" % (pw, pan, B), 60)
            if "True" in out: say("   ✓ chưa có gì tự mở bảng khi Windows lên → đã thêm lối tắt Startup (kèm --auto)")
            else: say("   ✗ chưa có gì tự mở bảng khi Windows lên — bảng CloudBlue → bấm 🔑 Tự đăng nhập + tự chạy"); probs.append("chưa tự chạy")
    if d.get("AUTOLOGON") == "1": say("   ✓ Windows tự đăng nhập: bật")
    else:
        say("   ⚠ Windows CHƯA tự đăng nhập → khởi động lại sẽ đứng ở màn hình mật khẩu, máy khách không chạy tới khi có người đăng nhập.\n"
            "     Sửa: bảng CloudBlue → bấm 🔑 Tự đăng nhập + tự chạy (tự gõ mật khẩu Windows vào bảng)")
        probs.append("Windows chưa tự đăng nhập (bấm 🔑 trong bảng)")
    return probs

# ------------------------------------------------------------------ 0. 17/11e: chạy cùng quyền với bảng CloudBlue
_WIN = os.name == "nt"
def is_admin():
    if not _WIN: return False
    try:
        import ctypes; return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False

def elev(pid):
    """Tiến trình chạy bằng quyền Admin? True / False / None (không đọc được). Cửa sổ thường bị từ chối đọc → coi là Admin."""
    if not _WIN: return None
    try:
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True); a = ctypes.WinDLL("advapi32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p; k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        a.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
        a.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
        hp = k.OpenProcess(0x1000, False, int(pid))                      # PROCESS_QUERY_LIMITED_INFORMATION
        if not hp: return None
        try:
            tok = ctypes.c_void_p()
            if not a.OpenProcessToken(hp, 0x0008, ctypes.byref(tok)):    # TOKEN_QUERY
                return True if ctypes.get_last_error() == 5 and not is_admin() else None
            try:
                e = ctypes.c_ulong(0); n = ctypes.c_ulong(0)
                if not a.GetTokenInformation(tok, 20, ctypes.byref(e), 4, ctypes.byref(n)): return None   # TokenElevation
                return bool(e.value)
            finally: k.CloseHandle(tok)
        finally: k.CloseHandle(hp)
    except Exception: return None

def priv_gate():
    """17/11e: lệnh A phải chạy CÙNG quyền với bảng CloudBlue (bảng chạy bằng quyền Admin). Khác quyền → máy bật từ lệnh này chạy quyền
       khác → MuMu báo xung đột ("Unable to start the Android Device … administrator privileges") và không bật được máy nào nữa.
       Trả None (chạy tiếp) hoặc câu báo (dừng, không đụng gì)."""
    if not _WIN: return None
    me = is_admin()
    pe = [elev(pid) for pid, _ in panel_procs()] + [elev(pid) for sv in ("cloudphoned", "bluestream", "cpapi") for pid, _ in procs(SVC_RX[sv])]
    ref = True if any(e is True for e in pe) else (False if any(e is False for e in pe) else None)
    if not me and ref is not False:
        return ("lệnh A đang chạy KHÔNG có quyền Admin" + (" mà bảng CloudBlue chạy bằng quyền Admin" if ref else "") + ".\n"
                "     Bật / khởi động lại máy từ cửa sổ này → giả lập chạy lẫn quyền, MuMu báo \"Unable to start the Android Device\" và\n"
                "     không bật được máy nào nữa. Đóng cửa sổ này → chuột phải nút Start → Terminal (Admin) (hoặc Windows PowerShell (Admin))\n"
                "     → dán lại lệnh A. Thanh tiêu đề cửa sổ phải có chữ \"Administrator\".")
    if me and ref is False:
        return ("bảng CloudBlue trên máy chủ này đang chạy KHÔNG có quyền Admin mà lệnh A chạy bằng quyền Admin → máy bật từ đây sẽ lẫn quyền.\n"
                "     Lần này: đóng cửa sổ này, mở PowerShell THƯỜNG (không Admin) rồi dán lại lệnh A (cùng quyền với bảng).\n"
                "     Muốn cả máy chủ chạy Admin (khuyên dùng): bảng → 🔑 Tự đăng nhập + tự chạy, rồi khởi động lại Windows lúc vắng khách.\n"
                "     ĐỪNG đóng bảng mở lại bằng Admin lúc máy ảo còn chạy — máy ảo cũ quyền thường + bảng Admin = lẫn quyền.")
    return None

PRIV_DONE = []
def priv_fix():
    """17/11e: máy ảo đang chạy sai quyền (bật từ lệnh A chạy KHÔNG Admin lần trước, mở MuMu bằng tay…) → phonectl quyen --sua:
       mở lại chương trình chính MuMu chạy sai quyền + tắt êm rồi bật lại đúng các máy khách chạy sai quyền."""
    say("4b/6 Quyền chạy của giả lập (lẫn Admin / quyền thường → MuMu báo xung đột, không bật được máy)")
    if not _WIN: say("   (bỏ qua — không phải Windows)"); return []
    if not ONLY_CHECK: say("   (bước này có thể mất 1–3 phút — trong lúc chờ ĐỪNG bấm gì trên bảng MuMu / đừng bấm \"Restart now\" của MuMu)")
    rc, out = pctl("quyen", *([] if ONLY_CHECK else ["--sua"]), t=1800)
    if "QUYEN_KQ" not in out:
        say("   ? phonectl chưa có lệnh kiểm quyền (bản cũ) — bỏ qua"); return []
    for ln in out.splitlines():
        if ln.startswith("   ") and ("lệnh này:" in ln or "máy đang chạy:" in ln or "sau khi sửa" in ln or "SAI QUYỀN" in ln
                                      or "✓" in ln or "✗" in ln or "⚠" in ln or "…" in ln): say(ln)
    kq = next((ln for ln in out.splitlines() if ln.startswith("QUYEN_KQ")), "")
    if kq.split()[1:2] == ["khong_can"]: return []          # 17/11e4: máy chủ LDPlayer / MEmu — không có lỗi xung đột quyền
    if kq.split()[1:2] in (["dung"], ["khong_biet"]): say("   ✓ giả lập chạy đúng 1 loại quyền"); return []
    if "bang_thuong" in kq:
        return ["bảng CloudBlue chạy quyền thường mà có máy chạy quyền Admin (lẫn quyền) → khởi động lại Windows lúc vắng khách"]
    m = re.search(r"da_sua=(\d+) chua_sua=(\d+)", kq)
    if m:
        if int(m.group(1)): PRIV_DONE.append(int(m.group(1)))
        if int(m.group(2)): return [f"{m.group(2)} máy chạy sai quyền chưa sửa được (xem dòng ⚠ / ✗ ở bước 4b) — chạy lại lệnh A sau 2 phút"]
        cs = re.search(r"con_sai=(\d+)", kq)
        if cs and int(cs.group(1)):
            return [f"sau khi sửa vẫn còn {cs.group(1)} tiến trình / máy chạy sai quyền (xem bước 4b) — chạy lại lệnh A sau 2 phút"]
        return []
    m = re.search(r"sai=(\d+)", kq)
    if m: return [f"{m.group(1)} máy chạy sai quyền Admin — chạy lệnh A (không --chi-kiem) bằng PowerShell (Admin) để bật lại đúng quyền"]
    if "khong_admin" in kq: return ["chưa sửa được máy chạy sai quyền — chạy lệnh A bằng PowerShell (Admin)"]
    return []

def panel_procs():
    out = ps("Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -match 'panel\\.py') -or $_.Name -eq 'BlueRobloxServer.exe' } | "
             "ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.Name }", 60)
    return [(int(q[0]), q[1]) for q in (ln.split() for ln in out.splitlines()) if len(q) == 2 and q[0].isdigit()]

def ensure_running(c):
    """Không dịch vụ nào chạy (bảng mở mà chưa bật gì / bảng chưa mở) → mở lại bảng CloudBlue kiểu TỰ BẬT A→Z."""
    sp = int(c.get("STREAM_PORT") or 8189)
    up = listening([8000, 8010, sp]) or set()
    if up or procs(SVC_RX["cloudphoned"]) or procs(SVC_RX["bluestream"]): return None
    pans = panel_procs()
    if ONLY_CHECK:
        say("   ✗ KHÔNG dịch vụ nào chạy (máy khách không bật, không nhận đơn) — mở bảng CloudBlue bấm ▶ Bật tất cả"); return "không dịch vụ nào chạy"
    if any(n.lower() == "bluerobloxserver.exe" for _, n in pans):
        say("   ✗ KHÔNG dịch vụ nào chạy — bảng BlueRobloxServer đang mở: bấm ▶ Bật tất cả trong bảng"); return "không dịch vụ nào chạy"
    for pid, _ in pans: kill(pid)
    if pans:
        time.sleep(2)
        if panel_procs():
            say("   ✗ KHÔNG dịch vụ nào chạy, mà không tắt được bảng CloudBlue đang mở (bảng chạy quyền Admin) → bấm ▶ Bật tất cả trong bảng")
            return "không dịch vụ nào chạy"
    try:
        subprocess.Popen([pythonw(), os.path.join(B, "panel.py"), "--auto"], cwd=B, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, creationflags=(0x00000008 | 0x00000200) if os.name == "nt" else 0)
    except Exception as e:
        say(f"   ✗ không mở được bảng CloudBlue ({e}) — mở tay rồi bấm ▶ Bật tất cả"); return "không mở được bảng"
    say(("   ⚠ bảng CloudBlue mở mà KHÔNG chạy dịch vụ nào → đã mở lại bảng kiểu tự bật A→Z" if pans else
         "   ⚠ bảng CloudBlue chưa mở, không dịch vụ nào chạy → đã mở bảng kiểu tự bật A→Z") + " — chờ dịch vụ lên (tối đa 3 phút)…")
    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(5)
        if procs(SVC_RX["cloudphoned"]) and (listening([sp]) or set()):
            say(f"   ✓ dịch vụ đã chạy sau {time.time() - t0:.0f} giây (bảng tự bật tiếp máy khách)"); return "LAUNCHED"
    say("   ✗ 3 phút dịch vụ vẫn chưa chạy — xem bảng CloudBlue (tab Tổng quan)"); return "dịch vụ chưa chạy"

# ------------------------------------------------------------------ 4. mạng / dịch vụ
def cf_status(host):
    """Hỏi https://<host>/ qua Cloudflare → 200 = tới được bộ phát hình (trả 'BlueRoblox stream v2') · 1033 = đường hầm KHÔNG NỐI
       (Cloudflare trả 530 / lỗi 1033) · 502 = hầm nối mà không tới cổng phát hình web · mã khác · 0 = không hỏi được."""
    try:
        with urllib.request.urlopen(urllib.request.Request("https://" + host + "/", headers={"User-Agent": "cloudblue-sua-tat-ca"}), timeout=12) as r:
            b = r.read(200)
            return 200 if r.status == 200 and b"stream v2" in b else 2000 + r.status if r.status == 200 else r.status
    except urllib.error.HTTPError as e:
        try: body = e.read(8000).decode("utf-8", "replace")
        except Exception: body = ""
        return 1033 if e.code == 530 or "Error 1033" in body else e.code
    except Exception:
        return 0

def cf_check(c, running):
    """15/11: dịch vụ cloudflared 'đang chạy' chưa chắc đường hầm đã NỐI. Hầm không nối → khách web / iPhone không mở được máy nào
       của máy chủ này (app / PC vẫn vào vì đi thẳng IP). Hỏi thử tên Cloudflare của máy chủ (STREAM_WS); lỗi 1033 → khởi động lại
       đường hầm rồi hỏi lại tối đa 30 giây. --chi-kiem: chỉ báo."""
    m = re.match(r"wss?://([A-Za-z0-9.-]+)", str(c.get("STREAM_WS") or "").strip())
    if not m: return []
    host = m.group(1); st = cf_status(host)
    if st == 0:
        say(f"   ? web qua Cloudflare ({host}): chưa hỏi thử được (máy chủ chưa ra mạng?)"); return []
    if st == 200:
        say(f"   ✓ web qua Cloudflare ({host}): thông"); return []
    if st == 2200:
        say(f"   ✗ web qua Cloudflare ({host}): trả về trang khác, không phải bộ phát hình — tên này đang trỏ nhầm chỗ?")
        return ["web qua Cloudflare trả trang lạ"]
    if st != 1033:
        say(f"   ✗ web qua Cloudflare ({host}): lỗi {st}" + (" — hầm nối mà không tới cổng phát hình web (xem dòng phát hình bên dưới)" if st == 502 else ""))
        return [f"web qua Cloudflare lỗi {st}"]
    say(f"   ✗ web qua Cloudflare ({host}): đường hầm KHÔNG NỐI (lỗi 1033) — khách web / iPhone không mở được máy nào ở máy chủ này")
    if ONLY_CHECK: return ["đường hầm Cloudflare không nối (lỗi 1033)"]
    if running: run(["sc", "stop", "cloudflared"], 40); time.sleep(4)
    run(["sc", "start", "cloudflared"], 40)
    for _ in range(6):                                   # hầm nối lại thường mất 5–20 giây
        time.sleep(5); st = cf_status(host)
        if st == 200: break
    if st == 200:
        say("     → đã khởi động lại đường hầm: ✓ web nối lại được"); return []
    say(f"     → đã khởi động lại đường hầm mà VẪN lỗi {st or '(không hỏi được)'} — xem mục 'Đường hầm Cloudflare' trong hướng dẫn")
    return [f"đường hầm Cloudflare vẫn lỗi {st or '?'} sau khi khởi động lại"]

def check_net(c):
    say("4/6 Dịch vụ + đường mạng")
    probs = []
    sp, wp = int(c.get("STREAM_PORT") or 8189), int(c.get("STREAM_WS_PORT") or 8020)
    up = listening([sp, wp, 8000, 8010])
    for lab, p in (("phát hình app (đi thẳng)", sp), ("phát hình qua Cloudflare", wp), ("trình phát hình web", 8000), ("cổng bảo vệ (cpapi)", 8010)):
        if up is None: say(f"   ? cổng {p} {lab}: không đọc được netstat"); continue
        say(f"   {'✓' if p in up else '✗'} cổng {p} {lab}: {'đang mở' if p in up else 'ĐÓNG'}")
        if p not in up and p in (sp, wp): probs.append(f"cổng {p} đóng")
    q = run(["sc", "query", "cloudflared"], 20)
    if "SERVICE_NAME" in q:
        okc = re.search(r":\s*4\s+RUNNING", q) is not None
        say(f"   {'✓' if okc else '✗'} đường hầm Cloudflare: {'đang chạy' if okc else 'KHÔNG CHẠY'}")
        if not okc:
            if not ONLY_CHECK: run(["sc", "start", "cloudflared"], 30); say("     → đã bật lại đường hầm"); time.sleep(10)
            probs.append("Cloudflare tắt")
        probs += cf_check(c, okc)
    ph = phones() or []
    a_c = sum(float(p.get("cpu") or 0) for p in ph); a_r = sum(float(p.get("ram") or 0) for p in ph)
    cap_c = float(c.get("CAP_CPU") or 100); cap_r = float(c.get("CAP_RAM") or 112)       # 16/11d: trần nhân 100 (trước 68)
    over = (cap_c > 0 and a_c >= cap_c) or (cap_r > 0 and a_r >= cap_r)
    say(f"   {'⚠' if over else '✓'} đã cấp {a_c:g} nhân · {a_r:g}GB cho {len(ph)} máy (trần {cap_c:g} nhân · {cap_r:g}GB)"
        + (" → ĐÃ ĐẦY: ngừng nhận máy mới tới khi xuống dưới trần (máy đang có vẫn chạy bình thường)" if over else ""))
    for svc in ("cloudphoned", "bluestream"):
        n = len(procs(SVC_RX[svc]))
        say(f"   {'✓' if n == 1 else '✗' if n == 0 else '⚠'} {SVC_VN[svc]}: " + ("đang chạy" if n == 1 else "KHÔNG chạy" if n == 0 else f"{n} bản cùng chạy (nên chỉ 1)"))
        if n != 1: probs.append(f"{SVC_VN[svc]}: {n} bản")
    return probs

# ------------------------------------------------------------------ 5. máy khách
def black(s):
    """Ảnh màn hình Android tối hết (< 0,3% điểm sáng)? None = không chụp được."""
    d = adb("-s", s, "exec-out", "screencap", t=25, raw=True)
    if len(d) < 16: return None
    w, h = struct.unpack("<II", d[:8]); n = w * h; hd = len(d) - n * 4
    if n <= 0 or hd not in (12, 16): return None
    st = max(1, n // 6000); tot = lit = 0
    for i in range(0, n, st):
        o = hd + 4 * i; tot += 1
        if d[o] > 24 or d[o + 1] > 24 or d[o + 2] > 24: lit += 1
    return lit * 1000 < tot * 3

def booted(s): return adb("-s", s, "shell", "getprop sys.boot_completed", t=12).strip() == "1"

def adb_ok(s):
    adb("connect", s, t=10)
    if adb("-s", s, "get-state", t=8).strip() == "device": return True, ""
    adb("disconnect", s, t=8); adb("connect", s, t=10)              # adb TCP hay kẹt "offline" → ngắt + nối lại
    if adb("-s", s, "get-state", t=8).strip() == "device": return True, "adb kẹt → đã nối lại"
    return False, ""

def focus(s):
    o = adb("-s", s, "shell", "dumpsys window | grep -m1 mCurrentFocus", t=15)
    m = re.search(r"\s([\w.]+)/", o)
    return m.group(1) if m else ("-" if "null" in o or not o.strip() else "?")

def is_home(pk): return pk in ("-", "?") or any(k in pk.lower() for k in HOME_PK)

# 16/11k: sổ khoá Android (keystore2) hỏng → Android sập / khởi động lại liên tục (màn đen, khách chờ mãi) — xem phonectl ksfix
KS_SH = ("[ $(id -u) = 0 ] || { echo KS_NOROOT; exit 0; }; F=/data/misc/keystore/persistent.sqlite; if [ ! -e $F ]; then echo KS_NOFILE; "
         "elif [ ! -s $F ]; then echo KS_EMPTY; elif ! H=$(head -c 6 $F); then echo KS_ERR; elif [ x$H = xSQLite ]; then echo KS_OK; else echo KS_BAD; fi")
def ks_bad(s):
    """16/11k2: lệnh kiểm không có dấu nháy, chỉ chạy khi đang là root; thử su -c · su 0 sh -c · adb đã là root. Không kiểm được → False."""
    for pre in ("su -c", "su 0 sh -c", ""):
        o = adb("-s", s, "shell", KS_SH if pre == "" else f"{pre} '{KS_SH}'", t=20)
        k = re.findall(r"KS_[A-Z]+", o)
        if k and k[-1] != "KS_NOROOT": return k[-1] == "KS_BAD"
    return False

def check_phone(p):
    nm = str(p["name"]); s = "127.0.0.1:%s" % p["port"]; r = {"name": nm, "s": s, "port": p["port"], "st": "OK", "note": "", "act": None}
    ok, note = adb_ok(s)
    if note: r["note"] += " (" + note + ")"
    if not ok: r.update(st="MẤT ADB", act="restart"); return r
    if not booted(s): r.update(st="CHƯA LÊN", act="restart"); return r
    if ks_bad(s):
        r.update(st="SỔ KHOÁ HỎNG", act="ksfix"); r["note"] += " — Android sẽ sập liên tục (màn đen) → sửa sổ khoá + khởi động lại"; return r
    w = adb("-s", s, "shell", "dumpsys power | grep -m1 mWakefulness=", t=10)
    if "mWakefulness=" in w and "Awake" not in w:
        adb("-s", s, "shell", "input keyevent 224", t=10); r["note"] += " (màn hình đang TẮT → đã bật sáng)"; time.sleep(1)
    adb("-s", s, "shell", "wm dismiss-keyguard; settings put system screen_off_timeout 2147483647; svc power stayon true", t=12)
    pk = focus(s); r["app"] = pk
    b = black(s)
    for _ in range(2):
        if not b: break
        time.sleep(4); b = black(s)
    if b is None: r.update(st="?"); r["note"] += " (không chụp được màn hình)"; return r
    if not b: return r
    if re.search(r"fl=[^\n]*\bSECURE\b", adb("-s", s, "shell", "dumpsys window windows", t=25)):
        r["note"] += " (app chặn chụp màn hình — không tính)"; return r
    if is_home(pk): r.update(st="ĐEN", act="restart"); return r
    r.update(st="ĐEN TRONG APP"); r["note"] += " — đang mở app/game (có thể game tắt hình để treo máy) → KHÔNG tự khởi động lại"
    return r

def sb_rows(c, q):
    url, key = c.get("SUPABASE_URL", "").rstrip("/"), c.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key: return None
    try:
        req = urllib.request.Request(url + "/rest/v1/" + q, headers={"apikey": key, "Authorization": "Bearer " + key, "User-Agent": "cloudblue-sua-tat-ca"})
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode() or "[]")
    except Exception:
        return None

GHOST = []

def remake_ghosts():
    """--lam-moi-may-ma: tạo lại máy MỚI (đúng cấu hình, bản Android, hạn) cho khách có máy "ma" còn hạn — remake.py, từng máy một."""
    if not GHOST: return []
    say(f"--- tạo lại {len(GHOST)} máy \"ma\" còn hạn (mỗi máy 2–5 phút, làm lần lượt) ---")
    code, out = run2([sys.executable, os.path.join(B, "run.py"), "remake.py", "all"], 4 * 3600)
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.startswith(("✓ ĐÃ LÀM MỚI", "✗", "=====")) or "ĐÃ LÀM MỚI" in ln: say("   " + ln[:170])
    m = re.search(r"ĐÃ LÀM MỚI (\d+)/(\d+)", out)
    return [m.group(1), m.group(2)] if m else []

def phones():
    try: return json.load(open(os.path.join(B, "redroid", "phones.json"), encoding="utf-8-sig")).get("phones", [])
    except Exception: return None

try: DISK_MIN_GB = float(os.environ.get("CB_DISK_MIN_GB") or 25)          # ổ đĩa còn dưới ngần này GB (hoặc dưới 7%) → dòng ✗ trong TÓM TẮT
except ValueError: DISK_MIN_GB = 25.0
DON = {}
def dondep():
    """17/11f — máy khách web đã HUỶ mà còn nằm trên máy chủ (lần xoá trước lỗi, khách huỷ lúc máy chủ tắt, máy mất tên…) → xoá hẳn máy ảo +
       dữ liệu ngay (phonectl dondep --xoa: CHỈ máy web ghi "đã huỷ"; máy đang thuê / không có trên web không bao giờ bị đụng). Chỉ kiểm → chỉ đếm."""
    code, out = pctl("dondep", *([] if ONLY_CHECK else ["--xoa"]), t=1800)
    m = re.search(r"DONDEP (\{.*\})", out or "")
    try: DON.update(json.loads(m.group(1)) if m else {})
    except Exception: pass
    if not m:
        last = ((out or "").strip().splitlines() or ["?"])[-1]
        if "invalid choice" not in (out or ""): say(f"   ⚠ chưa dọn được máy đã huỷ: {last[:160]}")
        return
    for ln in (out or "").splitlines():
        if ln.startswith(("🗑", "⚠")) or (ln.startswith("✗") and ONLY_CHECK): say("   " + ln.strip()[:200])
    if DON.get("deleted"): say(f"   ✓ đã xoá hẳn {DON['deleted']} máy khách web đã HUỶ còn sót trên máy chủ (máy ảo + dữ liệu) — nhả ổ đĩa")
    elif DON.get("dead") and ONLY_CHECK: say(f"   ⚠ {DON['dead']} máy khách web đã huỷ còn sót trên máy chủ — chạy lệnh A (không --chi-kiem) để xoá")
    if DON.get("lost_live"): say(f"   ⚠ {DON['lost_live']} máy khách ĐANG THUÊ bị mất tên trong giả lập — đã giữ nguyên (xem dòng ✓ đặt lại tên ở trên; còn thì chạy lại lệnh A sau 5 phút)")

def disk_report():
    """17/11f: ổ đĩa của máy chủ còn trống bao nhiêu (ổ chứa C:\\blue và ổ cài giả lập) → [(ổ, GB trống, GB tổng)], dòng cảnh báo nếu sắp đầy."""
    import shutil
    c = conf(); dirs = [B]
    for k in ("MUMU_DIR", "LD_DIR", "MEMU_DIR"):
        if c.get(k): dirs.append(c[k])
    try: dirs.append(open(os.path.join(B, "redroid", "mumu_dir.txt"), encoding="utf-8").read().strip())
    except OSError: pass
    dirs += [r"C:\Program Files\Netease\MuMuPlayer", r"C:\LDPlayer\LDPlayer9", r"D:\LDPlayer\LDPlayer9"]
    seen = {}; out = []; warn = []
    for d in dirs:
        if not d or not os.path.isdir(d): continue
        drv = os.path.splitdrive(os.path.abspath(d))[0].upper() or "/"
        if drv in seen: continue
        try: u = shutil.disk_usage(d)
        except OSError: continue
        seen[drv] = 1; fr, tot = u.free / 2 ** 30, u.total / 2 ** 30; out.append((drv, fr, tot))
        if fr < DISK_MIN_GB or (DISK_MIN_GB > 0 and fr / max(tot, 1) < 0.07): warn.append(f"ổ {drv} sắp ĐẦY: còn {fr:.0f}GB / {tot:.0f}GB — máy khách sẽ lỗi khi hết chỗ: huỷ bớt máy hết hạn, hoặc gửi Claude dòng này")
    return out, warn

def check_phones(c):
    say("5/6 Kiểm từng máy khách (nối adb · Android đã lên · bật sáng màn hình · màn đen)")
    if not os.path.isfile(PHONECTL): say("   - máy chủ này không có phonectl.py — bỏ qua"); return [], {}, []
    if not ONLY_CHECK:
        code, out = pctl("nhanlai", t=300)                  # máy còn trong giả lập mà mất khỏi danh sách, web còn thuê → nhận lại (giữ dữ liệu)
        for ln in out.splitlines():
            if ln.startswith("NHAN_LAI "): say("   ✓ " + ln[9:])
    dondep()                                                # 17/11f: máy khách web đã HUỶ còn sót (kể cả máy mất tên) → xoá hẳn ngay
    code, vl = pctl("vmlist", t=120)
    odd = [q[1].strip() for q in (ln.split(",") for ln in vl.splitlines()) if len(q) > 2 and q[0].strip().isdigit() and q[0].strip() != "0"
           and not q[1].strip().startswith(("cp_", "spare_", "tpl_"))]
    if odd: say(f"   ⚠ máy lạ trong giả lập (tên không phải máy khách): {', '.join(odd[:8])} — máy của khách ĐÃ HUỶ thì lệnh A đã tự xoá ở trên; "
                f"máy còn lại ở đây là máy khách đang thuê bị mất tên (tự đặt lại tên khi nằm đúng ô) hoặc máy không có trên web → ĐỪNG xoá khi chưa hỏi Claude")
    state = {}
    if ONLY_CHECK:                                          # chỉ kiểm: đọc giả lập, không ghi gì
        ph = phones()
        run_by = {q[1].strip(): q[2].strip() == "1" for q in (ln.split(",") for ln in vl.splitlines()) if len(q) > 2 and q[0].strip().isdigit()}
        for p in ph or []:
            nm = str(p.get("name"))
            if nm in run_by: state[nm] = "chạy" if run_by[nm] else ("ngủ" if p.get("hold") and p.get("sleep") else "tắt")
    else:
        code, lst = pctl("list", t=300)                     # đọc lại số máy / cổng thật trong giả lập (phonectl tự sửa cổng lệch)
        ph = phones()
        names = {str(p.get("name")) for p in ph or []}
        for ln in lst.splitlines():
            q = ln.split()
            if len(q) > 2 and q[0] in names and q[-1] in ("chạy", "ngủ", "tắt"): state[q[0]] = q[-1]
    if ph is None: say("   ✗ không đọc được redroid\\phones.json"); return [], {}, ["không đọc được phones.json"]
    if not ph: say("   (máy chủ chưa có máy khách nào)"); return [], {}, []
    ports = {}
    for p in ph: ports.setdefault(str(p.get("port")), []).append(str(p.get("name")))
    dup = {k: v for k, v in ports.items() if len(v) > 1 and k not in ("None", "", "0")}
    probs = []
    for k, v in dup.items(): say(f"   ✗ {len(v)} máy cùng cổng {k}: {', '.join(v)} — gửi Claude dòng này"); probs.append(f"trùng cổng {k}")
    node = c.get("NODE_ID", "")
    rows = sb_rows(c, "cloud_phones?node=eq.%s&status=in.(active,expired)&select=container,port,status,ram,cpu,android,expires_at" % urllib.parse.quote(node)) if node else None
    if rows is not None:
        byn = {str(p.get("name")): p for p in ph}
        ghost = [r["container"] for r in rows if r.get("container") and r["container"] not in byn]
        gact = [r for r in rows if r.get("container") in ghost and r.get("status") == "active"]
        GHOST[:] = gact
        lech = [r["container"] for r in rows if r.get("container") in byn and str(r.get("port")) != str(byn[r["container"]].get("port"))]
        if ghost:
            say(f"   ✗ {len(ghost)} máy \"ma\": web ghi khách đang thuê ở máy chủ này mà máy chủ KHÔNG còn máy (khách mở cứ quay 'Đang mở máy…'): "
                f"{', '.join(ghost[:8])}{' …' if len(ghost) > 8 else ''}")
            if gact:
                say(f"     trong đó {len(gact)} máy còn hạn — tổng {sum(float(r.get('cpu') or 0) for r in gact):g} nhân · {sum(float(r.get('ram') or 0) for r in gact):g}GB"
                    + ("" if REMAKE else " → muốn tạo lại máy MỚI cho khách (giữ cấu hình + hạn, dữ liệu cũ đã mất): chạy lại lệnh này kèm --lam-moi-may-ma"))
            if len(ghost) > len(gact): say(f"     {len(ghost) - len(gact)} máy đã hết hạn → nhận đơn tự ghi huỷ sau 30 phút")
            probs.append(f"{len(ghost)} máy ma (web còn, máy chủ không có)")
        if lech:
            say(f"   ⚠ {len(lech)} máy web ghi cổng khác máy chủ (app vẫn vào đúng, web xem có thể đen): {', '.join(lech[:8])}")
    now = datetime.datetime.now().astimezone()
    def exp_ok(p):
        try: return datetime.datetime.fromisoformat(str(p.get("expires")).replace("Z", "+00:00")) > now
        except Exception: return True
    run_l, sleep_n, held_n, off_l = [], 0, 0, []
    for p in ph:
        nm = str(p.get("name")); stv = state.get(nm, "")
        if p.get("hold"):
            if p.get("sleep"): sleep_n += 1
            else: held_n += 1
            continue
        if not str(p.get("port") or "").isdigit(): say(f"   - {nm}: chưa có cổng (đang tạo?) — bỏ qua"); continue
        if stv == "tắt" and exp_ok(p): off_l.append(p); continue
        if stv == "chạy" or not stv: run_l.append(p)
    res = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(check_phone, run_l): res.append(r)
    for r in sorted(res, key=lambda x: x["name"]):
        icon = "✓" if r["st"] == "OK" else "?" if r["st"] == "?" else "✗"
        say(f"   {icon} {r['name']:<16} cổng {r['port']:<6} {r['st']:<13} {r.get('app', '') if r['st'] != 'OK' else ''}{r['note']}")
    for p in off_l: say(f"   ✗ {p['name']:<16} cổng {p['port']:<6} ĐANG TẮT (còn hạn, không phải ngủ) → bật lại")
    say(f"   Máy đang ngủ (khách mở là tự bật): {sleep_n} · tạm dừng / khoá: {held_n}")
    return res, {"off": off_l, "sleep": sleep_n, "held": held_n, "ph": ph}, probs

# ------------------------------------------------------------------ 6. sửa
def busy(nm, cl):
    return re.search(r"phonectl\.py\S*\s+(wake|restart|create|resize|delete|start|waitboot|reconfig|ramfix)\s+" + re.escape(nm) + r"\b", cl) is not None

def fix_phones(res, extra):
    say("6/6 Sửa máy hỏng")
    bad = [r for r in res if r["act"]]
    if not bad and not extra.get("off"): say("   ✓ không có máy nào cần khởi động lại"); return [], []
    if ONLY_CHECK: say(f"   (chỉ kiểm — {len(bad) + len(extra.get('off', []))} máy cần sửa, chạy lại không kèm --chi-kiem để sửa)"); return [], []
    cl = py_cmdlines(); whole = re.search(r"phonectl\.py\S*\s+(bootall|heal)\b", cl)
    jobs = []; slow = []
    for r in bad:
        if busy(r["name"], cl): say(f"   - {r['name']}: đang được bật / sửa — để nó làm xong"); continue
        if r["st"] in ("CHƯA LÊN", "MẤT ADB"):
            slow.append(r); continue
        jobs.append(("ksfix" if r["act"] == "ksfix" else "restart", r["name"], r["s"], r["st"]))
    if slow:                                                  # có thể đang khởi động dở → chờ chung thêm 45 giây
        say(f"   … {len(slow)} máy chưa lên — chờ thêm 45 giây xem có tự lên không")
        t0 = time.time()
        while slow and time.time() - t0 < 45:
            time.sleep(9)
            for r in list(slow):
                if adb_ok(r["s"])[0] and booted(r["s"]): slow.remove(r); say(f"   ✓ {r['name']}: Android vừa lên — không cần khởi động lại")
        jobs += [("ksboot", r["name"], r["s"], r["st"]) for r in slow]
    for p in extra.get("off", []):
        if whole: say(f"   - {p['name']}: bảng đang bật lại máy khách hàng loạt — để bảng làm xong"); continue
        if not busy(str(p["name"]), cl): jobs.append(("start", str(p["name"]), "127.0.0.1:%s" % p["port"], "TẮT"))
    if not jobs: return [], []
    say(f"   Khởi động lại / bật {len(jobs)} máy (mỗi lúc 3 máy, mỗi máy 1–3 phút)…")
    lock = threading.Lock()
    def one(j):
        kind, nm, s, why = j
        if kind == "ksboot":                              # 16/11k2: máy chưa lên → canh sửa sổ khoá trước (máy hỏng sổ khoá khởi động lại bao nhiêu cũng không lên)
            code, out = pctl("ksfix", nm, "--cho", "150", t=1200)
            last = " / ".join(x.strip() for x in out.strip().splitlines()[-2:]) or "(không có kết quả)"
            if "đã sửa 1" in out:
                what = "file hệ thống Android hỏng do máy chủ bị tắt ngang" if "file hệ thống hỏng 1" in out else "sổ khoá Android hỏng"
                with lock: say(f"   ✓ {nm} ({why}) → {what}, đã sửa (giữ dữ liệu khách): {last[:160]}")
                return j, code
            if adb_ok(s)[0] and booted(s):
                with lock: say(f"   ✓ {nm} ({why}) → Android vừa lên — không cần khởi động lại")
                return j, 0
            if whole:
                with lock: say(f"   - {nm} ({why}) → sổ khoá không hỏng ({last[:90]}); bảng đang bật lại máy hàng loạt — để bảng làm xong")
                return None, code
            kind = "restart"
        code, out = pctl(*(["restart", nm, "--force"] if kind == "restart" else ["ksfix", nm, "--cho", "150"] if kind == "ksfix" else ["start", nm]), t=1200)
        last = " / ".join(x.strip() for x in out.strip().splitlines()[-2:]) or "(không có kết quả)"
        with lock: say(f"   {'✓' if code == 0 else '✗'} {nm} ({why}) → {'ép khởi động lại' if kind == 'restart' else 'sửa sổ khoá' if kind == 'ksfix' else 'bật lại'}: {last[:160]}")
        return j, code
    done = []
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for j, code in ex.map(one, jobs):
            if j is not None: done.append(j)
    say("   Chờ các máy vừa sửa lên (tối đa 5 phút)…")
    left = list(done); t0 = time.time(); final = []
    while left and time.time() - t0 < 300:
        time.sleep(10)
        for j in list(left):
            if adb_ok(j[2])[0] and booted(j[2]):
                left.remove(j); time.sleep(6)
                adb("-s", j[2], "shell", "input keyevent 224; wm dismiss-keyguard", t=10); time.sleep(2)
                b = black(j[2]); pk = focus(j[2])
                if b and is_home(pk):
                    say(f"   ✗ {j[1]}: Android đã lên nhưng VẪN ĐEN — gửi Claude dòng này"); final.append((j[1], "vẫn đen"))
                else:
                    say(f"   ✓ {j[1]}: Android đã lên, có hình — khách vào được"); final.append((j[1], "ok"))
    kham = kham_may([j[1] for j in left]) if left else {}      # 17/11g: vì sao máy vẫn không lên (chỉ đọc)
    for j in left:
        if REMAKE_BROKEN and str(j[1]).startswith("cp_"):
            say(f"   … {j[1]}: ép khởi động lại vẫn không lên → máy hỏng: xoá hẳn + tạo lại máy mới (giữ cấu hình + hạn, mất dữ liệu cũ)")
            code, out = pctl("delete", j[1], t=600)
            gone = "Đã xoá" in out or "không còn trong" in out
            if gone:
                code, out = run2([sys.executable, os.path.join(B, "run.py"), "remake.py", "one", j[1]], 1800)
                okm = "ĐÃ LÀM MỚI" in out and "1/1" in out
                say(f"   {'✓' if okm else '✗'} {j[1]}: " + ("đã tạo lại máy mới — khách vào được" if okm else "tạo lại CHƯA được — gửi Claude dòng này: "
                    + " / ".join(x.strip() for x in out.strip().splitlines()[-2:])[:160]))
                final.append((j[1], "ok" if okm else "tạo lại lỗi")); continue
            say(f"   ✗ {j[1]}: chưa xoá được máy hỏng: {' / '.join(x.strip() for x in out.strip().splitlines()[-2:])[:160]}")
        k = kham.get(j[1]) or ("", "")
        say(f"   ✗ {j[1]}: VẪN CHƯA LÊN sau 5 phút" + (f" — vì sao: {k[1][:230]}" if k[1] else " — chưa khám được vì sao")
            + " · KHÔNG xoá máy (dữ liệu khách còn trong ổ máy)")
        final.append((j[1], "chưa lên" + (f" [{k[0]}]" if k[0] else "")))
    return done, final

def mute_host(c):
    """17/11h: tắt tiếng loa Windows của máy chủ (`phonectl tattieng`). --chi-kiem hoặc HOST_MUTE=0 → không đụng. Trả câu cho TÓM TẮT ('' = không có)."""
    if ONLY_CHECK or str(c.get("HOST_MUTE", "1")).strip() == "0": return ""
    code, out = pctl("tattieng", t=150)
    m = re.search(r"TATTIENG (\S+) — (.*)", out)
    if not m: return ""                                      # phonectl cũ chưa có lệnh này
    say("   🔇 " + m.group(2).strip()[:200])
    return m.group(2).strip()[:120] if m.group(1) in ("done", "already") else ""

def kham_may(names):
    """17/11g: `phonectl khammay TÊN…` (chỉ đọc) cho các máy sửa rồi vẫn không lên → in chi tiết + trả {tên: (mã, câu kết luận)}."""
    names = [str(n) for n in names][:12]
    if not names: return {}
    say(f"   --- khám {len(names)} máy chưa lên (chỉ đọc, ~15 giây / máy) ---")
    code, out = pctl("khammay", *names, t=120 + 60 * len(names))
    res = {}
    for ln in out.splitlines():
        m = re.match(r"KHAMMAY (\S+): \[([A-Z]+)\] (.*)", ln.strip())
        if m: res[m.group(1)] = (m.group(2), m.group(3).strip()); continue
        if ln.startswith(("---", "   ")) and ln.strip() and "Traceback" not in ln: say("   " + ln.rstrip()[:230])
    if not res and "KHAMMAY" not in out:
        say("   ? phonectl chưa có lệnh khammay (bản cũ) — bỏ qua")
    return res

# ------------------------------------------------------------------ báo cáo thêm
def power_report():
    """17/11g: 3 ngày qua Windows bị TẮT NGANG mấy lần (sự kiện Kernel-Power 41: mất điện / bấm reset / treo cứng / sập)? Mỗi lần tắt ngang
       lúc máy khách đang chạy có thể làm hỏng file của Android trong máy đó. Chỉ ĐỌC nhật ký Windows. Trả [dòng cho phần TÓM TẮT]."""
    out = os.environ.get("CB_TEST_POWER")
    if out is None:
        if not _WIN: return []
        out = ps("$ErrorActionPreference='SilentlyContinue'; Get-WinEvent -FilterHashtable @{LogName='System';Id=41;ProviderName='Microsoft-Windows-Kernel-Power';"
                 "StartTime=(Get-Date).AddDays(-3)} | ForEach-Object { $d=@{}; ([xml]$_.ToXml()).Event.EventData.Data | ForEach-Object { $d[$_.Name]=$_.'#text' }; "
                 "'KP41|{0:dd}/{0:MM} {0:HH}:{0:mm}|{1}|{2}' -f $_.TimeCreated, $d['BugcheckCode'], $d['PowerButtonTimestamp'] }", 60)
    ev = [x.strip().split("|") for x in (out or "").splitlines() if x.strip().startswith("KP41|")]
    ev = [e for e in ev if len(e) >= 4]
    if not ev: return []
    crash = sum(1 for e in ev if e[2].strip() not in ("", "0"))
    how = ("Windows tự SẬP (màn hình xanh) " + str(crash) + " lần" if crash == len(ev) else
           "mất điện / bấm nút reset / treo cứng" if not crash else f"{crash} lần Windows tự sập, còn lại mất điện / bấm reset / treo cứng")
    say(f"--- máy chủ bị TẮT NGANG {len(ev)} lần trong 3 ngày qua (nhật ký Windows, Kernel-Power 41) ---")
    say("   lúc: " + " · ".join(e[1] for e in ev[:8]) + (" …" if len(ev) > 8 else ""))
    say(f"   kiểu: {how}. Mỗi lần tắt ngang lúc máy khách đang chạy có thể làm HỎNG FILE Android của máy đó (bản 17/11g tự sửa loại hay gặp).")
    return [f"3 ngày qua máy chủ bị TẮT NGANG {len(ev)} lần (gần nhất {ev[0][1]}; {how}) — đây là gốc làm máy khách hỏng. Cần khởi động lại máy chủ thì "
            "bấm nút trên web / chạy `python phonectl.py rebootserver`; ĐỪNG bấm reset, đừng tắt nguồn, đừng bấm \"Restart now\" của MuMu"]

def wake_report():
    """17/11h: khách mở máy đang NGỦ / TẮT hôm nay + hôm qua lên trong bao lâu, mấy lần lỗi, vì sao (dòng ☀ và 🩺 trong logs\\phat-hinh.log).
       Nhật ký chỉ ghi giờ (không ghi ngày) → đếm ngày bằng chỗ giờ nhảy lùi hơn 1 tiếng (qua nửa đêm). Chỉ ĐỌC."""
    okt, bad, why = [], [], {}; day = 0; prev = None
    for x in tail(os.path.join(LOGS, "phat-hinh.log"), 3000000):
        m = re.match(r"(\d\d):(\d\d):(\d\d) ", x)
        if m:
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if prev is None or 0 <= t - prev <= 82800: prev = t        # giờ đi tới bình thường
            elif t < prev - 3600: day += 1; prev = t                   # giờ nhảy lùi hơn 1 tiếng = qua nửa đêm, sang ngày mới
            # còn lại: dòng ghi lệch thứ tự quanh nửa đêm (lùi dưới 1 tiếng / vọt tới hơn 23 tiếng) → không tính
        m = re.search(r"☀ (\S+): Android đã lên sau (\d+) giây", x)
        if m: okt.append((day, int(m.group(2)))); continue
        m = re.search(r"☀ (\S+): LỖI — (.*?) \((\d+) giây\)\s*$", x)
        if m: bad.append((day, x[:8], m.group(1), m.group(2)[:110], int(m.group(3)))); continue
        m = re.search(r"🩺 KHAMMAY (\S+): \[([A-Z]+)\] (.*)", x)
        if m: why[m.group(1)] = (m.group(2), m.group(3).strip()[:170])
    old = sum(1 for q in bad if day - q[0] > 1)
    okt = sorted(sec for d, sec in okt if day - d <= 1); bad = [q for q in bad if day - q[0] <= 1]
    cu = f" · {old} lần lỗi cũ hơn trong nhật ký (bỏ qua)" if old else ""
    if not okt and not bad:
        if old: say(f"--- khách mở máy đang ngủ / tắt: hôm nay + hôm qua không có lần nào{cu} ---")
        return
    say(f"--- khách mở máy đang ngủ / tắt HÔM NAY + HÔM QUA: {len(okt)} lần lên được · {len(bad)} lần LỖI{cu} (logs\\phat-hinh.log) ---")
    if okt:
        slow = sum(1 for t in okt if t > 150)
        say(f"   lên được: thường {okt[len(okt) // 2]} giây · lâu nhất {okt[-1]} giây" + (f" · {slow} lần quá 150 giây (máy chủ bận / máy phải tự sửa)" if slow else ""))
    seen = set()
    for d, t, nm, msg, sec in bad[::-1]:
        if nm in seen or len(seen) >= 6: continue
        seen.add(nm)
        say(f"   ✗ {'hôm nay' if d == day else 'hôm qua'} {t} {nm}: {msg} ({sec} giây)" + (f" → khám: [{why[nm][0]}] {why[nm][1]}" if nm in why else ""))

def recent_report(c, res):
    node = c.get("NODE_ID", "")
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = sb_rows(c, "cloud_phones?node=eq.%s&created_at=gte.%s&select=container,status,android,replaces&order=created_at.desc&limit=60"
                   % (urllib.parse.quote(node), since)) if node else None
    if rows is None: return
    by = {r["name"]: r for r in res}
    new = [r for r in rows if r.get("container")]
    if not new: return
    sw = [r for r in new if r.get("replaces")]
    badn = [r for r in new if by.get(r["container"]) and by[r["container"]]["st"] not in ("OK", "?")]
    say(f"--- máy tạo 3 ngày qua trên máy chủ này: {len(new)} (đổi Android: {len(sw)}) · lỗi lúc kiểm: {len(badn)} ---")
    for r in badn[:20]:
        k = by[r["container"]]
        say(f"   {r['container']:<16} Android {r.get('android') or '?':<3} {'ĐỔI ANDROID · ' if r.get('replaces') else ''}{k['st']}")

def switch_report(c):
    """15/11: máy mới ĐỔI ANDROID đang "Lỗi" mà máy chủ này là nơi tạo lỗi lần cuối (3 ngày qua) → khách đang KHÔNG có máy.
       Chỉ ĐỌC + nhắc admin bấm 🔁 Tạo lại trên web (hạn dùng của khách vẫn giữ). Trả [dòng cho phần TÓM TẮT]."""
    node = c.get("NODE_ID", "")
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = sb_rows(c, "cloud_phones?node=eq.%s&status=eq.error&replaces=not.is.null&updated_at=gte.%s&select=name,android,error,updated_at"
                      "&order=updated_at.desc&limit=30" % (urllib.parse.quote(node), since)) if node else None
    if not rows: return []
    say(f"--- {len(rows)} máy ĐỔI ANDROID đang LỖI (tạo lỗi lần cuối ở máy chủ này) — khách đang không có máy ---")
    for r in rows[:10]:
        say(f"   {str(r.get('name') or '?')[:24]:<24} Android {str(r.get('android') or '?'):<3} {str(r.get('error') or '')[:110]}")
    say("   → web Quản trị › 📱 ĐT đám mây › Công cụ › 🧹 Máy đổi Android › 🔁 Tạo lại (hạn dùng của khách vẫn giữ)")
    return [f"{len(rows)} máy đổi Android đang lỗi — vào web bấm 🔁 Tạo lại (Công cụ › 🧹 Máy đổi Android)"]

def web_report():
    """15/11: khách WEB / iPhone gần đây đi đường nào, có ra hình không — chỉ ĐỌC logs\\phat-hinh.log:
       ▶ tên ← mã (đường, web) … ■ tên đóng (gửi N khung, bỏ M…) · S giây · lý do. Không in gì về khách ngoài 2 dòng nhật ký đó."""
    L = tail(os.path.join(LOGS, "phat-hinh.log"), 3000000)
    live, done = {}, []
    for x in L:
        m = re.search(r"▶ (\S+) ← \S+ \((\w+), (\w+)\)", x)
        if m:
            if m.group(3) == "web": live[m.group(1)] = (m.group(2), x[:8])
            else: live.pop(m.group(1), None)
            continue
        m = re.search(r"■ (\S+) đóng \(gửi (\d+) khung[^)]*\) · (\d+) giây(?: · (.*))?", x)
        if m and m.group(1) in live:
            k, t = live.pop(m.group(1)); done.append((k, int(m.group(2)), int(m.group(3)), (m.group(4) or "").strip(), t))
    wd = [x for x in L if "đường thẳng web" in x]
    if not done and not live and not wd: return
    nm = {"wsd": "thẳng", "ws": "Cloudflare", "direct": "thẳng (app)"}
    say(f"--- khách WEB / iPhone gần đây: {len(done)} phiên đã đóng · {len(live)} đang xem (logs\\phat-hinh.log) ---")
    if done:
        by = {}
        for k, *_ in done: by[k] = by.get(k, 0) + 1
        zero = sum(1 for _, n, *_ in done if n == 0); short = sum(1 for _, n, sec, *_ in done if n > 0 and sec < 8)
        say("   đường: " + " · ".join(f"{nm.get(k, k)} {n}" for k, n in sorted(by.items(), key=lambda kv: -kv[1]))
            + f" · không gửi được khung nào: {zero} · thoát dưới 8 giây: {short}")
        for k, n, sec, why, t in done[-6:]:
            say(f"   {t} {nm.get(k, k):<10} gửi {n} khung · {sec} giây" + (f" · {why[:70]}" if why else ""))
    else:
        say("   chưa có phiên web nào đóng trong nhật ký (khách iPhone không vào tới máy chủ, hoặc chưa ai dùng web)")
    if wd: say("   " + wd[-1].strip()[:170])

def ks_report():
    """16/11k2: các lần phonectl tự sửa sổ khoá Android hỏng (24 giờ qua). Nhiều máy bị ngay lúc vừa bật → máy mẫu có thể đang hỏng."""
    rows = []
    for x in tail(os.path.join(B, "redroid", "ks_events.log"), 60000):
        q = x.rstrip("\n").split("\t")
        try:
            if len(q) >= 3 and 0 <= (datetime.datetime.fromtimestamp(time.time()) - datetime.datetime.strptime(q[0], "%Y-%m-%d %H:%M:%S")).total_seconds() < 86400:
                rows.append(q)
        except (ValueError, OverflowError, OSError): pass
    if not rows: return []
    nf = sum(1 for q in rows if "file hệ thống hỏng" in q[2])
    say(f"--- Android hỏng file đã tự sửa 24 giờ qua: {len(rows)} lần — sổ khoá {len(rows) - nf} · file hệ thống {nf} (redroid\\ks_events.log) ---")
    for q in rows[-5:]: say(f"   {q[0][5:16]}  {q[1]:<16} {q[2]}")
    if nf: say("   (file hệ thống hỏng = máy chủ bị TẮT NGANG lúc máy đó đang chạy; đã đổi tên file hỏng, Android tự tạo lại, dữ liệu khách giữ nguyên)")
    new = len({q[1] for q in rows if "vừa bật" in q[2]})
    if new >= 3:
        say(f"   ⚠ {new} máy bị ngay lúc vừa bật → MÁY MẪU (tpl_a12 / tpl_a15) có thể đang hỏng: xoá máy mẫu trong MuMu, tạo máy mẫu mới (không bật), rồi chạy lại lệnh")
        return [f"{new} máy mới bị hỏng sổ khoá ngay lúc bật — nên làm lại máy mẫu"]
    return []

def log_report():
    try: ev = json.load(open(os.path.join(B, "redroid", "tusua.json"), encoding="utf-8")).get("events", [])
    except Exception: ev = []
    if ev:
        say("--- tự sửa gần nhất (redroid\\tusua.json) ---")
        for e in ev[-5:]: say("   " + time.strftime("%d/%m %H:%M", time.localtime(int(e.get("t", 0)))) + "  " + str(e.get("what", ""))[:150])
    T = [x for x in tail(os.path.join(LOGS, "bang-tu-sua.log"), 400000) if any(k in x for k in ("XOA", "KHOI_DONG_LAI", "NHAN_LAI", "GIU_LAI", "làm mới", "tạo lại"))]
    if T:
        say("--- bảng CloudBlue tự sửa gần nhất (logs\\bang-tu-sua.log) ---")
        for x in T[-5:]: say("   " + x[:170])
    L = tail(os.path.join(LOGS, "phat-hinh.log"))
    ks = ("lỗi bật hình", "ĐEN", "hình đen", "không ra khung", "ngừng ra hình", "lỗi quay", "không xuất được hình", "Traceback",
          "adb không thấy máy", "bật lại hình lỗi", "LỖI —")
    er = [x for x in L if any(k in x for k in ks)]
    if er:
        say(f"--- lỗi phát hình gần nhất ({len(er)} dòng trong nhật ký) ---")
        for x in er[-5:]: say("   " + x[:170])

def disk_line():
    """19/11a: 1 dòng TÓM TẮT về bộ nhớ máy khách — chỉ máy chủ MuMu có phonectl 19/11a trở lên; khác → ''."""
    try:
        cc = conf(); pc = open(PHONECTL, "rb").read()
        m = re.search(rb'PCTL_SUB = "(\d+)/(\d+)([a-z]?)"', pc)
        if not m or (int(m.group(2)), int(m.group(1)), m.group(3)) < (11, 19, b"a"): return ""
        if (cc.get("EMU") or "").strip().lower() != "mumu": return ""
        if str(cc.get("DISK_FIX", "1")).strip() == "0": return "bộ nhớ máy khách: ĐANG TẮT (DISK_FIX=0) — máy mới giữ cỡ ổ của máy mẫu, khách không mua thêm được"
        tiers = (cc.get("DISK_TIERS") or "0:8,4:13,8:16").strip()
        return (f"máy khách MỚI tự có bộ nhớ theo RAM (RAM:GB {tiers}; web chạy SQL v40 thì theo web) · khách mua thêm → nới ngay"
                " · máy cũ để nguyên — xem: python phonectl.py bonho")
    except Exception: return ""

def main():
    c = conf(); node = c.get("NODE_ID") or "?"
    say(f"== CloudBlue · sửa tất cả ({VER}) · máy chủ {node} · {time.strftime('%d/%m %H:%M')}" + (" · CHỈ KIỂM" if ONLY_CHECK else "") + " ==")
    probs = []
    g = priv_gate()                                         # 17/11e: chạy khác quyền với bảng → dừng NGAY, không đụng gì
    if g and not ONLY_CHECK:
        say("   ✗✗ DỪNG: " + g)
        say(f"== TÓM TẮT {node} ==")
        say("   ✗ chưa làm gì — xem dòng DỪNG ở trên (lệnh A phải chạy CÙNG quyền với bảng CloudBlue: PowerShell (Admin))")
        RUN["probs"] = ["dừng: " + g]
        return
    if g: say("   ⚠ " + g)
    changed, p = update_files(); probs += p
    RUN["changed"], RUN["p_upd"] = list(changed), list(p)
    probs += ld_fix(c, changed)
    p = restart_services(changed, {svc for gp, local, mark, svc in FILES if svc and os.path.isfile(os.path.join(B, local))
                                   and mark.encode() in open(os.path.join(B, local), "rb").read()})
    probs += p; RUN["p_rst"] = list(p)
    probs += fix_autostart()
    e = ensure_running(c)
    if e and e != "LAUNCHED": probs.append(e)
    probs += check_net(c)
    if e != "LAUNCHED":                                     # bảng vừa mở lại đang bật máy khách → để lượt sau (không chen lệnh vào giả lập)
        try: probs += mumu_tpl(c)
        except Exception as e_: say(f"   (kiểm máy mẫu MuMu lỗi: {e_})")
    hm = ""
    if e != "LAUNCHED":                                     # bảng vừa mở lại đang bật máy khách → không gọi thêm lệnh nào (chống kẹt tự tắt tiếng sau ≤ 10 phút)
        try: hm = mute_host(c)
        except Exception as e_: say(f"   (tắt tiếng máy chủ lỗi: {e_})")
    if e == "LAUNCHED":
        say("5/6 · 6/6 Bỏ qua kiểm máy khách: bảng CloudBlue vừa tự bật lại và đang bật lần lượt từng máy (vài phút) —\n"
            "    10 phút nữa chạy lại lệnh này để kiểm từng máy.")
        res, extra, done, final = [], {}, [], []
        probs.append("vừa mở lại bảng — 10 phút nữa chạy lại lệnh để kiểm máy khách")
    elif AUTO:
        say("5/6 · 6/6 Bỏ qua kiểm / sửa máy khách — đây là lượt TỰ CẬP NHẬT (chỉ thay bản mới + bật lại dịch vụ). Cần kiểm từng máy: chạy lệnh A bằng tay.")
        res, extra, done, final = [], {}, [], []
    else:
        probs += priv_fix()                                 # 17/11e: máy chạy sai quyền → bật lại đúng quyền TRƯỚC khi kiểm từng máy
        res, extra, p = check_phones(c); probs += p
        done, final = fix_phones(res, extra) if res or extra.get("off") else ([], [])
    rm = []
    if REMAKE and GHOST and not ONLY_CHECK: rm = remake_ghosts()
    recent_report(c, res)
    probs += switch_report(c)
    log_report()
    if not AUTO: probs += ks_report()
    web_report()
    try: wake_report()
    except Exception as e_: say(f"   (báo cáo mở máy lỗi: {e_})")
    pw = []
    try: pw = power_report()
    except Exception as e_: say(f"   (đọc nhật ký tắt ngang lỗi: {e_})")
    okn = sum(1 for r in res if r["st"] == "OK")
    inapp = [r["name"] for r in res if r["st"] == "ĐEN TRONG APP"]
    still = [n for n, k in final if k != "ok"]
    fixed_n = {j[1] for j in done}                       # 16/11k2: máy hỏng mà lần này chưa sửa (lệnh khác đang làm / bảng đang bật) → vẫn là CHƯA ổn
    left = [r["name"] for r in res if r["act"] and r["name"] not in fixed_n] + [str(p["name"]) for p in (extra or {}).get("off", []) if str(p["name"]) not in fixed_n]
    if left and not ONLY_CHECK: probs.append(f"{len(left)} máy chưa lên, lần này chưa sửa được ({', '.join(left[:6])}) — 5 phút nữa chạy lại lệnh A")
    disks, dwarn = disk_report(); probs += dwarn
    si = {}
    try:
        if e != "LAUNCHED":                                 # bảng vừa mở lại đang bật máy khách → không gọi thêm lệnh nào vào giả lập
            m_ = re.search(r"SERVERINFO (\{.*\})", pctl("serverinfo", t=120)[1] or ""); si = json.loads(m_.group(1)) if m_ else {}
    except Exception: pass
    say(f"== TÓM TẮT {node} ==")
    if changed: say("   ✓ đã cập nhật: " + ", ".join(sorted(set(changed))))
    if "panel" in changed: say("   (bảng CloudBlue bản mới chạy từ lần mở bảng / khởi động lại Windows kế tiếp — KHÔNG cần đóng bảng bây giờ)")
    if DON.get("deleted"): say(f"   ✓ đã xoá hẳn {DON['deleted']} máy khách đã huỷ còn sót (nhả ổ đĩa)")
    if disks: say("   ổ đĩa: " + " · ".join(f"{d} còn {fr:.0f}GB / {tot:.0f}GB" for d, fr, tot in disks))
    if si.get("boot_par"):
        say(f"   máy chủ khởi động lại → tự bật lại máy khách {si['boot_par']} máy cùng lúc, cách nhau {si.get('boot_gap', 20):g} giây (rảnh thì một nửa), "
            f"khách mở máy nào máy đó lên trước" + ("" if si.get("autologon") else " · ⚠ Windows CHƯA bật tự đăng nhập (bảng → 🔑) — khởi động lại sẽ đứng ở màn hình mật khẩu"))
        if str(si.get("boot_par")) == "1": say("   (đang đặt mỗi lúc chỉ bật 1 máy — máy chủ khoẻ nên để 2–4: `python phonectl.py setconf BOOTALL_PARALLEL=3`)")
    say(f"   máy khách: {okn} có hình · {len(done)} vừa sửa ({sum(1 for _, k in final if k == 'ok')} đã có hình)"
        + (f" · {extra.get('sleep', 0)} đang ngủ" if extra else "") + (f" · {len(inapp)} đen trong app (không đụng)" if inapp else ""))
    if rm: say(f"   ✓ đã tạo lại {rm[0]}/{rm[1]} máy \"ma\" cho khách")
    if PRIV_DONE: say(f"   ✓ đã bật lại {sum(PRIV_DONE)} máy chạy sai quyền (lẫn Admin — MuMu hết báo xung đột)")
    if hm: say("   🔇 " + hm + " — máy chủ tự giữ tắt tiếng (bật lại: python phonectl.py tattieng --bat · thôi tự tắt: python phonectl.py setconf HOST_MUTE=0)")
    try:                                                    # 18/11a: luật máy khách tự ngủ đang dùng ở máy chủ này (phonectl cũ không báo → không in)
        if "idle_h" in si:
            ih = float(si.get("idle_h") or 0)
            say(f"   💤 máy khách tự ngủ: chỉ khi {ih:g} giờ liền không ai mở máy và máy không có việc gì (đang treo game / mở app thì KHÔNG bao giờ bị tắt)"
                if ih > 0 else "   💤 máy khách tự ngủ: ĐANG TẮT ở máy chủ này (IDLE_STOP_MIN=0 / IDLE_STOP_H=0) — máy không bao giờ tự ngủ")
    except (TypeError, ValueError): pass
    dl = disk_line()                                        # 19/11a: bộ nhớ máy khách theo cấu hình + mua thêm
    if dl: say("   💾 " + dl)
    for x in probs: say("   ✗ " + x)
    for n in still: say(f"   ✗ {n}: sửa rồi vẫn {dict(final).get(n)}")
    for x in pw: say("   ⚠ " + x)
    RUN["probs"] = list(probs) + [f"{n}: sửa rồi vẫn {dict(final).get(n)}" for n in still]; RUN["done"] = True
    say("   → XONG, máy chủ ổn." if not probs and not still else "   → Còn dòng ✗ ở trên: chụp phần TÓM TẮT gửi Claude.")

if __name__ == "__main__":
    if not state_begin():
        say(f"== CloudBlue · sửa tất cả ({VER}) · tự cập nhật: đang có lượt cập nhật khác chạy dở — thôi =="); sys.exit(0)
    try: main()
    finally: state_end()
