package shop.blueroblox.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Màn đăng nhập / đăng ký / quên mật khẩu (dùng chung tài khoản với web cloudblue.vn). */
public class LoginActivity extends Activity {
    private int mode = 0; // 0 đăng nhập · 1 đăng ký · 2 quên mật khẩu
    private LinearLayout form;
    private TextView err, title, sub;
    private EditText user, mail, pass, pass2;
    private Button go;
    private TextView[] tabs = new TextView[2];

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Ui.init(this);
        if (Api.loggedIn()) { openMain(); return; }
        Ui.edgeToEdge(this);

        LinearLayout root = Ui.col(this, 18);
        root.setPadding(Ui.dp(24), Ui.dp(36), Ui.dp(24), Ui.dp(28));
        root.setGravity(Gravity.CENTER_HORIZONTAL);

        ImageView logo = Ui.whale(this, 120);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(Ui.dp(176), Ui.dp(120));
        lp.gravity = Gravity.CENTER_HORIZONTAL;
        root.addView(logo, lp);

        title = Ui.h1(this, "");
        android.text.SpannableString bn = new android.text.SpannableString("CloudBlue");   // "Blue" màu xanh giống logo
        bn.setSpan(new android.text.style.ForegroundColorSpan(Ui.LIGHT ? Ui.BLUE : Color.rgb(90, 168, 255)), 5, 9, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        title.setText(bn);
        title.setGravity(Gravity.CENTER);
        root.addView(title, Ui.fill());
        sub = Ui.muted(this, Ui.L("Điện thoại Android chạy 24/7 trên cloud — thuê và điều khiển ngay trên điện thoại của bạn.",
                "Android phones running 24/7 in the cloud — rent and control them right from your phone."));
        sub.setGravity(Gravity.CENTER);
        root.addView(sub, Ui.fill());

        // Thanh chọn Đăng nhập / Đăng ký
        LinearLayout seg = Ui.row(this, 6);
        seg.setPadding(Ui.dp(4), Ui.dp(4), Ui.dp(4), Ui.dp(4));
        seg.setBackground(Ui.ringed(Ui.PANEL, 16));
        for (int i = 0; i < 2; i++) {
            final int m = i;
            tabs[i] = Ui.chip(this, i == 0 ? Ui.L("Đăng nhập", "Log in") : Ui.L("Đăng ký", "Sign up"), i == 0);
            tabs[i].setOnClickListener(v -> setMode(m));
            seg.addView(tabs[i], Ui.weight(1));
        }
        root.addView(seg, Ui.fill());

        form = Ui.col(this, 12);
        user = Ui.input(this, Ui.L("Tên đăng nhập (VD: hien123)", "Username"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        mail = Ui.input(this, "Email", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        pass = Ui.input(this, Ui.L("Mật khẩu", "Password"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        pass2 = Ui.input(this, Ui.L("Nhập lại mật khẩu", "Repeat password"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        form.addView(user, Ui.fill());
        form.addView(mail, Ui.fill());
        form.addView(pass, Ui.fill());
        form.addView(pass2, Ui.fill());
        err = Ui.text(this, "", 13.5f, Ui.BAD, false);
        form.addView(err, Ui.fill());
        go = Ui.button(this, "", Ui.PRIMARY);
        go.setOnClickListener(v -> submit());
        form.addView(go, Ui.fill());
        TextView forgot = Ui.text(this, Ui.L("Quên mật khẩu?", "Forgot password?"), 14, Ui.SKY, false);
        forgot.setGravity(Gravity.CENTER);
        forgot.setPadding(0, Ui.dp(6), 0, Ui.dp(6));
        forgot.setOnClickListener(v -> setMode(mode == 2 ? 0 : 2));
        form.addView(forgot, Ui.fill());
        root.addView(form, Ui.fill());

        TextView policy = Ui.text(this, Ui.L("Dùng app là bạn đồng ý Điều khoản & Chính sách của CloudBlue.",
                "By using the app you agree to CloudBlue Terms & Policy."), 12, Ui.MUTED, false);
        policy.setGravity(Gravity.CENTER);
        policy.setOnClickListener(v -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Api.policyUrl()))));
        root.addView(policy, Ui.fill());

        ScrollView sv = Ui.scroll(this, root);
        sv.setBackground(Ui.bubbles(this));
        Ui.insets(sv, true, true);
        setContentView(sv);
        setMode(0);
    }

    private void setMode(int m) {
        mode = m;
        Ui.setChip(tabs[0], m == 0 || m == 2);
        Ui.setChip(tabs[1], m == 1);
        user.setVisibility(m == 1 ? View.VISIBLE : View.GONE);
        pass.setVisibility(m == 2 ? View.GONE : View.VISIBLE);
        pass2.setVisibility(m == 1 ? View.VISIBLE : View.GONE);
        go.setText(m == 0 ? Ui.L("Đăng nhập", "Log in") : m == 1 ? Ui.L("Tạo tài khoản", "Create account") : Ui.L("Gửi email đặt lại mật khẩu", "Send reset email"));
        err.setText("");
        err.setTextColor(Ui.BAD);
    }

    private void submit() {
        final String u = user.getText().toString().trim(), e = mail.getText().toString().trim(), p = pass.getText().toString();
        if (!e.contains("@")) { err.setText(Ui.L("Nhập email hợp lệ.", "Enter a valid email.")); return; }
        if (mode != 2 && p.length() < 6) { err.setText(Ui.L("Mật khẩu phải từ 6 ký tự.", "Password must be at least 6 characters.")); return; }
        if (mode == 1) {
            if (!u.matches("^[A-Za-z0-9_.]{3,24}$")) { err.setText(Ui.L("Tên đăng nhập 3–24 ký tự: chữ, số, _ .", "Username: 3–24 letters, numbers, _ .")); return; }
            if (!p.equals(pass2.getText().toString())) { err.setText(Ui.L("Hai mật khẩu không khớp.", "Passwords do not match.")); return; }
        }
        go.setEnabled(false);
        go.setAlpha(.6f);
        err.setText("");
        if (mode == 0) {
            Api.bg(() -> { Api.login(e, p); return true; }, ok -> openMain(), this::fail);
        } else if (mode == 1) {
            Api.bg(() -> Api.signup(u, e, p), in -> {
                if (in) { openMain(); return; }
                done();
                setMode(0);
                mail.setText(e);
                err.setTextColor(Ui.OK);
                err.setText(Ui.L("Đã tạo tài khoản! Mở email để xác nhận, rồi đăng nhập.", "Account created! Confirm your email, then log in."));
            }, this::fail);
        } else {
            Api.bg(() -> { Api.recover(e); return true; }, ok -> {
                done();
                err.setTextColor(Ui.OK);
                err.setText(Ui.L("Đã gửi email đặt lại mật khẩu. Mở hộp thư để làm tiếp.", "Reset email sent. Check your inbox."));
            }, this::fail);
        }
    }

    private void done() { go.setEnabled(true); go.setAlpha(1f); }

    private void fail(String m) { done(); err.setTextColor(Ui.BAD); err.setText(m); }

    private void openMain() {
        Intent main = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        String pid = getIntent() != null ? getIntent().getStringExtra("open_phone") : null;   // mở từ link blueroblox://phone/… → đăng nhập xong vào thẳng máy đó
        if (pid != null && !pid.isEmpty()) startActivities(new Intent[]{main, new Intent(this, ControlActivity.class).putExtra("id", pid)});
        else startActivity(main);
        finish();
    }
}
