package shop.blueroblox.app;

import android.app.Activity;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.LauncherActivityInfo;
import android.content.pm.LauncherApps;
import android.os.Bundle;
import android.os.Process;
import android.os.UserHandle;
import android.os.UserManager;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Biểu tượng "Clone 1/2/3/4" trên màn hình chính của MÁY CLOUD (MEmu):
 * màn hình chính MEmu không có tab Công việc (Work) → bấm biểu tượng này để mở bản clone số N
 * (app đầu tiên không phải app hệ thống trong hồ sơ clone thứ N). Server tự bật/tắt các biểu tượng (pm enable/disable).
 */
public class CloneLaunch extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        try { open(); } catch (Exception e) { Toast.makeText(this, "Chưa mở được bản clone: " + e.getMessage(), Toast.LENGTH_LONG).show(); }
        finish();
    }

    private void open() {
        String cls = getIntent().getComponent() != null ? getIntent().getComponent().getClassName() : "";
        int n = 1;
        try { n = Integer.parseInt(cls.replaceAll("\\D+", "")); } catch (Exception ignored) { }
        LauncherApps la = (LauncherApps) getSystemService(Context.LAUNCHER_APPS_SERVICE);
        final UserManager um = (UserManager) getSystemService(Context.USER_SERVICE);
        List<UserHandle> ps = new ArrayList<>(la.getProfiles());
        ps.remove(Process.myUserHandle());
        Collections.sort(ps, (a, c) -> Long.compare(um.getSerialNumberForUser(a), um.getSerialNumberForUser(c)));
        if (ps.size() < n) { Toast.makeText(this, "Chưa có bản clone " + n + " — tạo trong Clone tab trên web.", Toast.LENGTH_LONG).show(); return; }
        UserHandle u = ps.get(n - 1);
        for (LauncherActivityInfo i : la.getActivityList(null, u)) {
            ApplicationInfo ai = i.getApplicationInfo();
            if ((ai.flags & ApplicationInfo.FLAG_SYSTEM) != 0 || ai.packageName.equals(getPackageName())) continue;
            la.startMainActivity(i.getComponentName(), u, null, null);
            return;
        }
        Toast.makeText(this, "Bản clone " + n + " chưa có app.", Toast.LENGTH_LONG).show();
    }
}
