# Đưa BLUEROBLOX lên mạng tại blueroblox.shop

Làm lần lượt từ bước 1 đến bước 9. Mất khoảng 1–2 giờ. Không cần biết lập trình, chỉ cần copy/dán đúng chỗ.

## Trong thư mục này có gì
| File | Dùng để |
|---|---|
| `index.html`, `styles.css`, `app.js` | Giao diện web (trang khách + trang admin) |
| `config.js` | Nơi dán 2 khoá Supabase (bước 2) |
| `api/sepay-webhook.js` | Nhận thông báo tiền vào từ SePay, tự cộng tiền cho khách |
| `api/notify.js`, `api/telegram.js`, `api/_lib.js` | Bot Telegram báo đơn, giao VPS bằng Reply, gửi email |
| `supabase/schema.sql` | Tạo toàn bộ cơ sở dữ liệu |
| `supabase/seed.sql` | Sản phẩm mẫu (không bắt buộc) |

## Chi phí dự kiến
- Tên miền `blueroblox.shop`: khoảng 30.000–100.000đ năm đầu (gia hạn khoảng 600.000–900.000đ/năm, xem kỹ giá gia hạn trước khi mua).
- Supabase, Vercel: **miễn phí** ở mức shop nhỏ.
- SePay: có gói miễn phí giới hạn số giao dịch, gói trả phí từ khoảng 99.000đ/tháng.
- Gửi email (Resend): miễn phí 3.000 email/tháng.

---

## Bước 1 – Mua tên miền blueroblox.shop
1. Vào một nhà bán tên miền: Namecheap, Porkbun, Hostinger, hoặc trong nước như Tenten, Mắt Bão, PA Việt Nam.
2. Tìm `blueroblox.shop` và mua. **Tắt** các dịch vụ kèm theo như hosting hay email, vì không cần.
3. Chưa cần chỉnh gì thêm. Bước 5 sẽ trỏ tên miền về web.

## Bước 2 – Tạo cơ sở dữ liệu Supabase
1. Vào **supabase.com** › Sign up bằng GitHub hoặc email › **New project**.
   - Name: `blueroblox`
   - Database password: đặt mật khẩu mạnh và lưu lại.
   - Region: **Southeast Asia (Singapore)**, gần Việt Nam nên nhanh nhất.
2. Chờ khoảng 2 phút cho project tạo xong. Vào **SQL Editor › New query**, mở file `supabase/schema.sql`, copy **toàn bộ** nội dung vào, rồi bấm **Run**. Thấy chữ "Success" là xong.
3. (Không bắt buộc) Làm tương tự với `supabase/seed.sql` để có sẵn sản phẩm mẫu.
4. Vào **Project Settings › API**, copy 2 giá trị:
   - **Project URL** (dạng `https://abcxyz.supabase.co`)
   - **anon public** key
5. Mở file `config.js`, dán 2 giá trị đó vào thay cho `YOUR-PROJECT...` và `YOUR-ANON-KEY`.
6. Cũng ở trang API đó, copy thêm **service_role** key và cất riêng. Khoá này chỉ dán ở bước 4, tuyệt đối không dán vào `config.js` hay gửi cho ai.

### Cài đặt đăng nhập và email (vẫn trong Supabase)
7. **Authentication › URL Configuration**:
   - Site URL: `https://blueroblox.shop`
   - Redirect URLs: thêm `https://blueroblox.shop` và `https://www.blueroblox.shop`
8. **Authentication › Email Templates › Reset Password**: thay nội dung bằng đoạn dưới để khách nhận **mã 6 số**:
   ```html
   <h2>BLUEROBLOX – Khôi phục mật khẩu</h2>
   <p>Mã khôi phục của bạn là:</p>
   <h1 style="letter-spacing:6px">{{ .Token }}</h1>
   <p>Mã có hiệu lực trong 1 giờ. Nếu bạn không yêu cầu, hãy bỏ qua email này.</p>
   ```
   Subject: `Mã khôi phục mật khẩu BLUEROBLOX`
9. **Confirm signup** template: sửa sang tiếng Việt nếu muốn. Muốn khách đăng ký xong dùng được ngay mà không cần xác nhận email thì vào **Authentication › Sign In / Providers › Email** và tắt **Confirm email**.
10. **Gửi email thật (nên làm):** email mặc định của Supabase chỉ gửi được vài email mỗi giờ. Đăng ký **resend.com**, thêm tên miền `blueroblox.shop`, làm theo hướng dẫn thêm bản ghi DNS. Sau đó vào Supabase › **Authentication › Emails › SMTP Settings** và điền thông tin SMTP của Resend:
    - Host `smtp.resend.com`, Port `465`, User `resend`, Password = API key của Resend.
    - Sender: `no-reply@blueroblox.shop`

## Bước 3 – Đưa mã nguồn lên GitHub
1. Vào **github.com**, tạo tài khoản, rồi bấm **New repository**. Đặt tên `blueroblox`, chọn **Private**, bấm Create.
2. Bấm **uploading an existing file**, kéo **tất cả file và thư mục** trong gói này vào (giữ nguyên thư mục `api` và `supabase`), rồi bấm **Commit changes**.

## Bước 4 – Chạy web trên Vercel
1. Vào **vercel.com**, chọn **Sign up with GitHub**, rồi **Add New › Project** và chọn repo `blueroblox`.
2. Framework Preset: **Other**. Để trống Build Command và Output Directory.
3. Mở **Environment Variables** và thêm 3 biến:
   | Name | Value |
   |---|---|
   | `SUPABASE_URL` | Project URL ở bước 2 |
   | `SUPABASE_SERVICE_ROLE_KEY` | service_role key ở bước 2 |
   | `SEPAY_API_KEY` | Một chuỗi bí mật bạn tự đặt, dài khoảng 30 ký tự ngẫu nhiên. Lưu lại để dùng ở bước 7 |
4. Bấm **Deploy**. Xong bạn có một link tạm dạng `blueroblox.vercel.app`, mở thử xem web đã lên chưa.

## Bước 5 – Gắn tên miền blueroblox.shop
1. Trong Vercel, vào project › **Settings › Domains**, thêm `blueroblox.shop` và `www.blueroblox.shop`.
2. Vào trang quản lý DNS ở nơi bạn mua tên miền, thêm đúng những bản ghi mà Vercel hiện ra. Thường là:
   | Loại | Tên (Host) | Giá trị |
   |---|---|---|
   | A | `@` | `76.76.21.21` |
   | CNAME | `www` | `cname.vercel-dns.com` |
   Xoá các bản ghi A hoặc CNAME cũ trùng tên (nếu có). **Nếu Vercel hiện giá trị khác, dùng giá trị Vercel hiện.**
3. Chờ 5–30 phút. Khi Vercel báo **Valid Configuration**, web đã chạy ở `https://blueroblox.shop` (có sẵn HTTPS).

## Bước 6 – Tạo tài khoản ADMIN
1. Mở `https://blueroblox.shop`, bấm **Đăng ký** và tạo tài khoản bằng email của bạn, ví dụ tên đăng nhập `lehien261125`.
2. Vào Supabase › **SQL Editor**, chạy câu lệnh sau (thay đúng email bạn vừa đăng ký):
   ```sql
   update public.profiles set role = 'admin' where email = 'email-cua-ban@gmail.com';
   ```
3. Quay lại web, đăng xuất rồi đăng nhập lại. **Bảng quản trị tự mở ra.** Khách thường đăng nhập thì không bao giờ thấy phần này.
4. Trong bảng quản trị:
   - **Ngân hàng:** nhập tài khoản nhận tiền, rồi Lưu.
   - **Nội dung trang:** điền Zalo, Email, Discord, Chính sách.
   - **Sản phẩm:** thêm sản phẩm. Với VPS, bấm **"Mẫu 7 · 15 · 30 ngày"** rồi điền giá từng gói, hoặc **"+ Thêm gói"** để tự đặt số ngày.
   - Bấm **Nhập kho** ở từng sản phẩm, dán hàng thật vào, **mỗi dòng 1 sản phẩm**. Ví dụ: Clone là `user|pass`, VPS là `IP:port|user|pass`. Khi khách mua VPS, web tự ghi thêm ngày hết hạn theo gói khách chọn.

## Bước 7 – Nối ngân hàng để tự cộng tiền (SePay)
1. Đăng ký **sepay.vn** và thêm tài khoản ngân hàng nhận tiền. Phải là **đúng tài khoản** bạn đã nhập ở tab Ngân hàng.
2. Vào **Tích hợp WebHooks › Thêm webhooks**:
   - Bắt sự kiện: **Có tiền vào**.
   - Gọi đến URL: `https://blueroblox.shop/api/sepay-webhook`
   - Kiểu chứng thực: **API Key**, dán đúng chuỗi `SEPAY_API_KEY` bạn đặt ở bước 4.
   - Trạng thái: Kích hoạt.
3. Bấm **Gửi thử**. Kết quả trả về `{"success":true...}` là đã nối được.

## Bước 8 – Thử toàn bộ trước khi mở bán
1. Đăng ký một tài khoản khách khác (dùng email phụ).
2. Bấm **Nạp**, tạo QR **10.000đ**, rồi quét bằng app ngân hàng và chuyển thật.
3. Trong khoảng 1–2 phút, màn hình phải báo **"Nạp thành công"** và số dư tăng.
4. Mua thử 1 sản phẩm có hàng trong kho. Vào **Đơn hàng** phải thấy thông tin được giao.
5. Thử **Quên mật khẩu**: email phải nhận được mã 6 số, nhập mã rồi đặt mật khẩu mới.
6. Vào admin kiểm tra các tab Khách hàng, Nạp tiền và Đơn hàng: phải hiện đúng dữ liệu vừa thử.

Nếu nạp tiền mà không cộng: vào SePay › Nhật ký webhook xem lỗi, kiểm tra lại `SEPAY_API_KEY` trên Vercel và nội dung chuyển khoản. Lệnh nạp bị kẹt thì vào admin › Nạp tiền › **Duyệt tay**.

## Bước 9 – Bot Telegram báo đơn và giao VPS bằng Reply
1. Mở Telegram, tìm **@BotFather**, gõ `/newbot`, rồi đặt tên và username cho bot (username phải kết thúc bằng `bot`). BotFather sẽ gửi **TOKEN**, dạng `123456:ABC...`.
2. Vào Vercel › project › **Settings › Environment Variables** và thêm các biến sau:
   | Name | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | TOKEN vừa nhận |
   | `TELEGRAM_WEBHOOK_SECRET` | Một chuỗi bí mật bạn tự đặt (chỉ chữ và số, khoảng 30 ký tự) |
   | `NOTIFY_SECRET` | Một chuỗi bí mật khác, cũng tự đặt |
   | `ADMIN_EMAIL` | Gmail của bạn, để nhận thêm email khi có đơn (không bắt buộc) |
   | `RESEND_API_KEY` | API key Resend ở bước 2, để gửi email cho khách (không bắt buộc) |

   Thêm xong thì vào **Deployments**, bấm **⋯ › Redeploy**.
3. Mở trình duyệt, dán link dưới (thay TOKEN và SECRET bằng giá trị của bạn), rồi Enter. Thấy chữ `Webhook was set` là xong:
   `https://api.telegram.org/botTOKEN/setWebhook?url=https://blueroblox.shop/api/telegram&secret_token=SECRET`
4. Mở bot của bạn trên Telegram và gõ `/id`. Bot trả về **Chat ID**. Thêm biến `TELEGRAM_CHAT_ID` với số đó trên Vercel, rồi **Redeploy** lần nữa.
5. Vào Supabase › **Database › Webhooks › Create a new hook** và tạo **2 hook**:
   - Hook 1: Table `orders`, Events: **Insert** và **Update**.
   - Hook 2: Table `topups`, Events: **Update**.
   - Cả 2 hook đều chọn Type **HTTP Request**, Method **POST**, URL `https://blueroblox.shop/api/notify`, và thêm HTTP Header `x-webhook-secret` = giá trị `NOTIFY_SECRET`.
6. Vào trang admin, sửa sản phẩm VPS và tick **"Giao thủ công"**, rồi đặt **Số đơn còn nhận được**.

**Cách giao hàng hằng ngày:**
- Khách mua xong, bot gửi tin **🚨 ĐƠN CẦN GIAO**.
- Bạn **Reply** tin đó, dán thông tin máy (ví dụ ID và mật khẩu UltraView), mỗi dòng 1 máy. Web tự giao cho khách, tự thêm ngày hết hạn theo gói, và gửi email cho khách.
- Không giao được thì Reply `/hoantien`, tiền tự trả về số dư của khách.
- Bạn cũng có thể giao trong trang admin: tab **Đơn hàng › Giao hàng**.

---

## Cập nhật web sau này
- **Sửa sản phẩm, giá, nội dung, ngân hàng:** làm ngay trong bảng quản trị, không cần đụng mã.
- **Thêm tính năng mới:** sửa file, rồi tải lên lại GitHub (repo › Add file › Upload files, chọn đè file cũ). Vercel tự cập nhật sau khoảng 1 phút. Dữ liệu khách không bị ảnh hưởng.
- Khi `schema.sql` có thay đổi, chạy lại phần thay đổi trong SQL Editor.

## Giữ an toàn
- `service_role` key và `SEPAY_API_KEY` chỉ nằm trong Environment Variables của Vercel.
- Không chia sẻ mật khẩu admin, và bật xác thực 2 lớp cho tài khoản GitHub, Vercel, Supabase và SePay.
- Ghi rõ trong Chính sách rằng mua bán tài khoản game có thể vi phạm điều khoản của nhà phát hành, nên acc có thể bị khoá.
