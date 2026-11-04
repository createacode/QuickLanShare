# Windows 从零搭建 Android 编译环境（通用模板 · 以 cmd 为主）

> **这是一份通用模板**，适用于任何用 Gradle 构建的 Android 项目，不绑定某个具体仓库。
> 文中出现的 `<...>` 和几个变量需要按你的项目替换：
> `%JAVA_HOME%`、`%ANDROID_HOME%`、`%PROJECT%`、`%GRADLE_VER%`、`%COMPILE_SDK%`、`%BUILD_TOOLS%`。
> 环境目录沿用一套固定约定：**Java 放 `D:\Develop\SERVE\JAVA`，安卓环境放 `D:\Develop\SERVE\Android`**。
> 命令在 **命令提示符（cmd）** 中执行；只有"把路径加入用户 PATH"这一步建议用图形界面，原因见 3.2、3.3。

---

## 全流程一览（11 步）

| 步骤 | 做什么 | 完成标志 |
| --- | --- | --- |
| 第一步 | 查清项目要求（Gradle / compileSdk / AGP / JDK） | 记下 4 个版本号 |
| 第二步 | 建目录骨架 | `%JAVA_HOME%`、`%ANDROID_HOME%` 两个空目录 |
| 第三步 | 设置环境变量 | `JAVA_HOME`、`ANDROID_HOME` 已写入用户变量 |
| 第四步 | 重开 cmd，确认变量 | `echo %JAVA_HOME%` 有输出 |
| 第五步 | 安装 JDK | `java -version` 正常 |
| 第六步 | 安装 cmdline-tools | `android.exe --version` 正常 |
| 第七步 | 安装 SDK 组件（platform / build-tools / platform-tools） | `platforms\android-*`、`build-tools\*` 就位 |
| 第八步 | 准备 Gradle（项目 wrapper） | `gradlew.bat --version` 正常 |
| 第九步 | 编译 | 生成 `app-debug.apk` |
| 第十步 | 安装到手机 | 桌面出现图标 |
| 第十一步 | 环境自检 | 各项输出符合预期 |

---

## 第一步：先查清项目要什么

不同项目要求的版本不一样，**先读项目文件，再装环境**，不要凭感觉装最新版。

在项目根目录执行（把路径换成你的项目）：

```cmd
cd /d D:\path\to\your\project

rem 1) Gradle 版本：看 distributionUrl 里的 gradle-x.y.z-bin.zip
findstr /c:"distributionUrl" gradle\wrapper\gradle-wrapper.properties

rem 2) compileSdk / targetSdk / buildToolsVersion：看 app 模块的构建文件
findstr /c:"compileSdk" app\build.gradle app\build.gradle.kts 2>nul
findstr /c:"targetSdk" app\build.gradle app\build.gradle.kts 2>nul
findstr /c:"buildToolsVersion" app\build.gradle app\build.gradle.kts 2>nul

rem 3) AGP 与 Kotlin 版本：看根构建文件或版本目录
findstr /c:"com.android.application" build.gradle build.gradle.kts gradle\libs.versions.toml 2>nul
```

记下四个值，后面都要用：

| 变量 | 含义 | 示例 |
| --- | --- | --- |
| `%GRADLE_VER%` | wrapper 要的 Gradle 版本 | `9.5.0` |
| `%COMPILE_SDK%` | 编译用 SDK 平台 | `37` |
| `%BUILD_TOOLS%` | 构建工具版本 | `37.0.0` |
| JDK | AGP 要求的 JDK | `17` |

把查到的值设成当前窗口的变量（换窗口要重设；下文命令直接用）：

```cmd
set "PROJECT=D:\path\to\your\project"
set "GRADLE_VER=9.5.0"
set "COMPILE_SDK=37"
set "BUILD_TOOLS=37.0.0"
```

> 上面的版本号只是示例，必须替换成第一步查到的实际值。

**版本对应关系（常见，最终以项目与 AGP release notes 为准）**

| AGP | 最低 Gradle | JDK | compileSdk 上限（发布时参考） |
| --- | --- | --- | --- |
| 8.x | 8.x，按 AGP 具体版本要求 | 17 | 34–36 |
| 9.x | 9.x，按 AGP 具体版本要求 | 17 | 36+ |

> 不确定就以项目 `gradle-wrapper.properties` 里的 Gradle 版本为准；AGP 会在启动时校验，版本低了会直接报
> `Minimum supported Gradle version is x.y`。

**系统与资源要求**

| 项 | 要求 |
| --- | --- |
| 系统 | Windows 10/11 x64（1803+ 自带 `curl.exe`、`tar.exe`） |
| 磁盘 | D 盘空闲 ≥ 20 GB（SDK + Gradle 依赖缓存） |
| 网络 | 能访问 `dl.google.com`、`repo.maven.apache.org`；Gradle 官方下载会转到 GitHub，国内常不稳 |
| 权限 | 装到 `D:\Develop` 与改"用户环境变量"都不需要管理员 |

---

## 第二步：建目录骨架

```cmd
mkdir "D:\Develop\SERVE"
mkdir "D:\Develop\SERVE\JAVA"
mkdir "D:\Develop\SERVE\Android"
mkdir "D:\Develop\SERVE\Android\AndroidSDK"
```

```text
D:\Develop\SERVE\
├── JAVA\            ← 将来的 %JAVA_HOME%
└── Android\
    └── AndroidSDK\  ← 将来的 %ANDROID_HOME%
```

---

## 第三步：设置环境变量

| 变量名 | 值 | 作用 |
| --- | --- | --- |
| `JAVA_HOME` | `D:\Develop\SERVE\JAVA` | JDK 根目录，Gradle 靠它找 Java |
| `ANDROID_HOME` | `D:\Develop\SERVE\Android\AndroidSDK` | SDK 根目录，Gradle 靠它找 SDK |
| `PATH` 追加 3 条 | `%JAVA_HOME%\bin`、`%ANDROID_HOME%\platform-tools`、`%ANDROID_HOME%\cmdline-tools\latest\bin` | 让 `java`、`adb`、`android` 全局可用 |

> `ANDROID_HOME` 指向 **`AndroidSDK` 这一层**，不是 `D:\Develop\SERVE\Android`。

### 3.1 写入 JAVA_HOME 与 ANDROID_HOME

```cmd
setx JAVA_HOME "D:\Develop\SERVE\JAVA"
setx ANDROID_HOME "D:\Develop\SERVE\Android\AndroidSDK"

rem 当前窗口也立刻生效（setx 只影响以后新开的窗口）
set "JAVA_HOME=D:\Develop\SERVE\JAVA"
set "ANDROID_HOME=D:\Develop\SERVE\Android\AndroidSDK"
```

### 3.2 把三条路径加入用户 PATH（图形界面最稳）

1. `Win + R` → `sysdm.cpl` → 「高级」→「环境变量」；
2. 在「用户变量」里选中 `Path` →「编辑」→「新建」，逐条添加：
   - `%JAVA_HOME%\bin`
   - `%ANDROID_HOME%\platform-tools`
   - `%ANDROID_HOME%\cmdline-tools\latest\bin`
3. 一路「确定」，然后**重新打开 cmd**。

### 3.3 为什么不用 `setx PATH "%PATH%;..."`

- `setx PATH "%PATH%;..."` 会把**系统 PATH + 用户 PATH 的合并结果**整条写进用户变量，造成重复与污染；
- 合并后的字符串可能超过 1024 字符，被静默截断，导致部分命令突然找不到；
- 图形界面修改的是用户 `Path`，类型为 `REG_EXPAND_SZ`，能正确展开 `%JAVA_HOME%`，也不会动系统变量。

### 3.4 三个常见坑

| 坑 | 说明 |
| --- | --- |
| `setx` 后当前窗口没变 | `setx` 只对**以后新开**的进程生效，当前窗口要用 `set` 或重开 |
| 用 `setx` 改 PATH | 会合并、污染甚至截断 PATH，见 3.3 |
| PATH 用逗号分隔 | Windows 只认 `;`，逗号会让整段失效（`adb`、`android` 找不到） |

---

## 第四步：重开 cmd，确认变量

关掉当前窗口，重新打开一个 cmd：

```cmd
echo %JAVA_HOME%
echo %ANDROID_HOME%
echo %PATH%
where java
where adb
```

期望：前两条打印目录；`%PATH%` 里能看到展开后的三条路径；`where` 能定位到 `java.exe` 与 `adb.exe`（此时 JDK 还没装，`where java` 可能暂时找不到，装完第五步再验一次）。

> 看不到就检查：是否重开了窗口、变量建在了「用户变量」还是「系统变量」。

同时把项目相关变量也设上（这些只在当前窗口有效）：

```cmd
set "PROJECT=D:\path\to\your\project"
set "GRADLE_VER=9.5.0"
set "COMPILE_SDK=37"
set "BUILD_TOOLS=37.0.0"
```

---

## 第五步：安装 JDK

### 5.1 选版本

按第一步查到的 AGP 要求装：主流是 **JDK 17**（AGP 8/9 都用它），少数新项目要 21。
**必须是 JDK，不是 JRE**（需要 `javac`）。

| 来源 | 地址 |
| --- | --- |
| Microsoft OpenJDK 17（免登录，推荐） | <https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip> |
| 清华 Adoptium 镜像 | <https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/windows/> |
| Oracle JDK | <https://www.oracle.com/java/technologies/downloads/#java17> |

需要 JDK 21 时，把下面命令中的 `17` 换成 `21`，并确认 AGP 与 Gradle 支持。

```cmd
curl -fL -o "%USERPROFILE%\Downloads\jdk17.zip" https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip
```

> `-f` 让 HTTP 404/500 直接失败，避免把错误页当成 zip 存下来。

### 5.2 解压到 `%JAVA_HOME%`

zip 里通常多一层 `jdk-17.x.x`，用 `tar` 剥掉：

```cmd
if not exist "%JAVA_HOME%" mkdir "%JAVA_HOME%"
tar -xf "%USERPROFILE%\Downloads\jdk17.zip" -C "%JAVA_HOME%" --strip-components 1
```

没有 `tar` 就用 7-Zip 解压，然后把 `jdk-17.x.x\` **里面的内容**复制到 `%JAVA_HOME%`。

### 5.3 验证

```cmd
"%JAVA_HOME%\bin\java.exe" -version
"%JAVA_HOME%\bin\javac.exe" -version
java -version
where java
```

前两条输出 17.x；第三条能跑说明 PATH 生效。
判断标准：存在 `%JAVA_HOME%\bin\java.exe`（不是 `%JAVA_HOME%\jdk-17\bin\java.exe`）。

---

## 第六步：安装 cmdline-tools

### 6.1 下载并解压

```cmd
curl -fL -o "%TEMP%\ct.zip" https://dl.google.com/android/repository/commandlinetools-win-16111833_latest.zip

rem 先清掉上次残留，避免旧文件混进新目录
if exist "%TEMP%\ct" rd /s /q "%TEMP%\ct"
mkdir "%TEMP%\ct"
tar -xf "%TEMP%\ct.zip" -C "%TEMP%\ct"

rem 已有旧版本先改名备份，避免覆盖失败
if not exist "%ANDROID_HOME%\cmdline-tools" mkdir "%ANDROID_HOME%\cmdline-tools"
if exist "%ANDROID_HOME%\cmdline-tools\latest" move "%ANDROID_HOME%\cmdline-tools\latest" "%ANDROID_HOME%\cmdline-tools\latest.bak.%RANDOM%"

move "%TEMP%\ct\cmdline-tools" "%ANDROID_HOME%\cmdline-tools\latest"
```

**层级必须正确**：最终是 `%ANDROID_HOME%\cmdline-tools\latest\bin\...`，
不是 `cmdline-tools\cmdline-tools\bin`。

> 如果 `latest` 已存在，`move` 会变成"移动到子目录"，正好产生上面这个错误层级。所以务必先备份或删除 `latest`。

### 6.2 验证

```cmd
"%ANDROID_HOME%\cmdline-tools\latest\bin\android.exe" --version
```

输出 `1.0.x` 即正常。

> cmdline-tools 23.0 起自带的工具是 **Android CLI（`android.exe`）**；`sdkmanager.bat` 仍在，但只是兼容壳，
> 会打印弃用警告。`sdkmanager --version` 显示的是 Android CLI 版本，不是 23.0，这是官方新行为。

### 6.3 解压不完整怎么办

症状：`NoClassDefFoundError: com/android/sdklib/...`，或找不到 `sdkmanager.bat` / `android.exe`。

```cmd
rem 列出 0 字节文件（命令行直接粘贴用 %f，写进 .bat 时改成 %%f）
for /r "%ANDROID_HOME%\cmdline-tools\latest" %f in (*) do @if %~zf==0 echo [0 byte] %f
```

有输出就删掉整个 `latest` 重新解压（建议 7-Zip）。

---

## 第七步：安装 SDK 组件

### 7.1 查准确包名

包名要按项目 `compileSdk` 来，且新版平台目录可能带小版本号（如 `android-37.0`）：

```cmd
"%ANDROID_HOME%\cmdline-tools\latest\bin\android.exe" --sdk="%ANDROID_HOME%" sdk list --all | findstr /i "platforms/android-%COMPILE_SDK%"
"%ANDROID_HOME%\cmdline-tools\latest\bin\android.exe" --sdk="%ANDROID_HOME%" sdk list --all | findstr /i "build-tools/%BUILD_TOOLS%"
```

把查到的完整包名设成变量，后面统一使用，避免复制错：

```cmd
set "PLATFORM_PKG=platforms/android-37.0"
set "BUILD_TOOLS_PKG=build-tools/37.0.0"
```

> 这里的 `37.0` / `37.0.0` 只是示例，以 7.1 的输出为准。

### 7.2 安装

```cmd
"%ANDROID_HOME%\cmdline-tools\latest\bin\android.exe" --sdk="%ANDROID_HOME%" sdk install platform-tools %PLATFORM_PKG% %BUILD_TOOLS_PKG%
```

许可由 Android CLI 自动处理，通常不需要额外的 `--licenses`；若提示许可未接受，按提示执行并确认。

| 包 | 用途 |
| --- | --- |
| `platform-tools` | adb / fastboot |
| `platforms/android-<版本>` | 编译平台，必须匹配项目的 compileSdk |
| `build-tools/<版本>` | aapt2 / d8 / zipalign，匹配项目的 buildToolsVersion |

### 7.3 验证

```cmd
dir /b "%ANDROID_HOME%\platforms"
dir /b "%ANDROID_HOME%\build-tools"
findstr ApiLevel "%ANDROID_HOME%\platforms\android-37.0\source.properties"
dir "%ANDROID_HOME%\build-tools\37.0.0\aapt2.exe"
"%ANDROID_HOME%\platform-tools\adb.exe" version
"%ANDROID_HOME%\cmdline-tools\latest\bin\android.exe" --sdk="%ANDROID_HOME%" sdk list
```

期望：对应平台的目录存在、`ApiLevel` 与 compileSdk 一致、`aapt2.exe` 有几 MB、adb 能打印版本。
（`android-37.0`、`37.0.0` 同样替换成实际目录名。）

### 7.4 手动兜底（工具装不上时）

平台的包名与 zip 名可在 SDK 仓库索引里查（<https://dl.google.com/android/repository/repository2-3.xml>），
下载后解压到 `platforms\android-<版本>` 或 `build-tools\<版本>` 即可：

```cmd
curl -fL -o "%TEMP%\platform.zip" https://dl.google.com/android/repository/platform-37.0_r02.zip
mkdir "%ANDROID_HOME%\platforms\android-37.0"
tar -xf "%TEMP%\platform.zip" -C "%ANDROID_HOME%\platforms\android-37.0"
```

---

## 第八步：准备 Gradle

Gradle **不用单独安装**：项目自带 wrapper（`gradlew.bat` + `gradle\wrapper\gradle-wrapper.properties`），
首次运行会按 `distributionUrl` 下载 `%GRADLE_VER%` 到
`%USERPROFILE%\.gradle\wrapper\dists\`。

### 8.1 方式 A：直接跑（网络好时）

```cmd
cd /d %PROJECT%
gradlew.bat --version
```

期望输出 Gradle 版本与 JVM 版本（JVM 应是你装的 JDK）。

### 8.2 方式 B：改用国内镜像（推荐国内网络）

编辑 `gradle\wrapper\gradle-wrapper.properties`，**只替换域名，文件名（即版本号）保持项目原样**：

```properties
# 原文示例
distributionUrl=https\://services.gradle.org/distributions/gradle-9.5.0-bin.zip

# 腾讯云镜像（9.5.0 只是示例，必须与项目原版本一致）
distributionUrl=https\://mirrors.cloud.tencent.com/gradle/gradle-9.5.0-bin.zip

# 或华为云
distributionUrl=https\://repo.huaweicloud.com/gradle/gradle-9.5.0-bin.zip
```

> 不要照抄示例里的 `9.5.0`：以项目原 `distributionUrl` 中的版本为准。
> 镜像文件与官方一致时 `distributionSha256Sum` 不用改；若报校验失败，说明镜像文件不同，应改回官方或核对校验和。

### 8.3 方式 C：离线（已有 zip，或完全不通外网）

把 zip 放在本地任意目录，然后把 `distributionUrl` 指向它（注意 `file\:///` 的转义和**正斜杠**）：

```properties
distributionUrl=file\:///D:/Develop/SERVE/gradle/gradle-9.5.0-bin.zip
```

再执行 `gradlew.bat --version`，wrapper 会直接解压本地文件，不再联网。
（之后若改回官方 URL，wrapper 会因为缓存目录不同而重新下载；想长期离线就保留本地路径。）

### 8.4 验证

```cmd
cd /d %PROJECT%
gradlew.bat --version
```

---

## 第九步：编译

```cmd
cd /d %PROJECT%
gradlew.bat assembleDebug --stacktrace
```

- 首次构建会下载 AGP、Kotlin、Compose 等依赖（0.5–1 GB，5–20 分钟，取决于网络）；
- 多数项目的产物在：`app\build\outputs\apk\debug\app-debug.apk`
  （多模块项目可能是 `模块名\build\outputs\apk\debug\`）；
- `release` 包需要签名配置，本文只覆盖 debug；
- 依赖已缓存且不想联网时，可加 `--offline`。

---

## 第十步：安装到手机

手机开启「开发者选项 → USB 调试」，连接后允许调试：

```cmd
adb devices
adb install -r "<apk 完整路径>"
```

`adb` 不在 PATH 时用全路径：`"%ANDROID_HOME%\platform-tools\adb.exe"`。
`devices` 列表里显示 `unauthorized` 时，在手机上点「允许 USB 调试」。

---

## 第十一步：环境自检

逐项执行，全部符合预期即可开始开发：

```cmd
rem JDK
java -version
where java

rem Android 工具链
"%ANDROID_HOME%\cmdline-tools\latest\bin\android.exe" --version
"%ANDROID_HOME%\platform-tools\adb.exe" version
dir /b "%ANDROID_HOME%\platforms"
dir /b "%ANDROID_HOME%\build-tools"

rem 项目 wrapper（在项目根目录）
cd /d %PROJECT%
gradlew.bat --version

rem 项目文件是否齐全（按实际模块调整）
if exist gradlew.bat (echo [OK] gradlew.bat) else (echo [FAIL] gradlew.bat)
if exist app\build.gradle.kts (echo [OK] app build file) else (echo [FAIL] app build file)
if exist gradle\wrapper\gradle-wrapper.properties (echo [OK] wrapper properties) else (echo [FAIL] wrapper properties)
```

判定：`java -version` 显示 17.x；`adb version` 有输出；`android.exe --version` 显示 1.0.x；
`gradlew.bat --version` 输出项目要求的 Gradle 版本；三个 `if exist` 全部为 `[OK]`。

---

## 附录 A：常见错误速查

| 报错 / 现象 | 原因 | 处理 |
| --- | --- | --- |
| `'java' 不是内部或外部命令` | PATH 没生效 / 没装 JDK | 重开 cmd；检查 `%JAVA_HOME%\bin\java.exe`；按第三步加 PATH |
| `SDK location not found` | `ANDROID_HOME` 没设或指向错层 | 指向 `...\AndroidSDK`，重开 cmd |
| `Failed to find target with hash string 'android-XX'` | 没装对应 platform | 第七步装 `platforms/android-XX` |
| `Failed to install the following Android SDK packages` | build-tools 缺失 | 第七步装对应 build-tools |
| `Minimum supported Gradle version is x.y` | Gradle 版本低于 AGP 要求 | 用项目 wrapper 指定版本 |
| `Unsupported class file major version` | JDK 版本与 AGP 要求不符 | 换 JDK（多数项目为 17） |
| `NoClassDefFoundError: com/android/sdklib/...` | cmdline-tools 解压不完整 | 6.3 删掉重解 |
| `aapt2.exe` 0 字节 / 不是有效的 Win32 程序 | build-tools 包损坏 | 删掉该 build-tools 重装 |
| Gradle 下载超时/卡住 | 官方链路落到 GitHub | 8.2 镜像、8.3 离线或附录 G |
| `'tar'` / `'curl'` 不是内部或外部命令 | 系统太旧或精简版 | 用 7-Zip / 浏览器下载 |
| `adb: no devices` / `unauthorized` | 没开 USB 调试 / 没允许授权 | 开调试、点允许、换线 |
| 终端中文乱码 | 代码页不是 UTF-8 | `chcp 65001` |

---

## 附录 B：下载地址汇总

| 用途 | 地址 |
| --- | --- |
| JDK 17（Microsoft） | <https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip> |
| JDK 17（清华 Adoptium） | <https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/windows/> |
| cmdline-tools（最新） | <https://dl.google.com/android/repository/commandlinetools-win-16111833_latest.zip> |
| SDK 仓库索引（查包名/zip 名） | <https://dl.google.com/android/repository/repository2-3.xml> |
| Gradle 官方 | <https://services.gradle.org/distributions/> |
| Gradle 腾讯镜像 | <https://mirrors.cloud.tencent.com/gradle/> |
| Gradle 华为镜像 | <https://repo.huaweicloud.com/gradle/> |

---

## 附录 C：装完后的目录结构

```text
D:\Develop\SERVE\
├── JAVA\                        ← %JAVA_HOME%
│   ├── bin\{java.exe, javac.exe, ...}
│   └── lib\  conf\  release
└── Android\
    └── AndroidSDK\              ← %ANDROID_HOME%
        ├── cmdline-tools\latest\{bin, lib}
        ├── platforms\android-<版本>\{android.jar, source.properties}
        ├── build-tools\<版本>\{aapt2.exe, d8.bat, zipalign.exe}
        ├── platform-tools\{adb.exe, fastboot.exe}
        └── licenses\

%USERPROFILE%\.gradle\
├── wrapper\dists\gradle-<版本>-bin\<hash>\...
└── caches\modules-2\...        ← 构建依赖缓存
```

---

## 附录 D：国内网络加速

1. **Gradle 发行版**：8.2 镜像或 8.3 离线。
2. **Google Maven**（拉不到 AGP 时）：在 `settings.gradle(.kts)` 的
   `pluginManagement.repositories` 和 `dependencyResolutionManagement.repositories` 里，
   把下面三条放到 `google()` 之前：

   ```kotlin
   maven { url = uri("https://maven.aliyun.com/repository/google") }
   maven { url = uri("https://maven.aliyun.com/repository/central") }
   maven { url = uri("https://maven.aliyun.com/repository/plugin") }
   ```

---

## 附录 E：版本对应速查

| 项目里看到的 | 需要装 |
| --- | --- |
| `distributionUrl=...gradle-9.5.0-bin.zip` | Gradle 由 wrapper 自动处理 |
| `compileSdk = 37` / `release(37)` | `platforms/android-37.0`（以 `sdk list` 为准） |
| `buildToolsVersion = "37.0.0"` | `build-tools/37.0.0` |
| AGP 9.x | JDK 17 + 对应 Gradle 9.x |
| AGP 8.x | JDK 17 + 对应 Gradle 8.x |

---

## 附录 F：卸载 / 重装 / 迁移

```cmd
rem 删除 JDK / SDK（先关闭占用它们的程序：IDE、Gradle、adb）
rd /s /q "%JAVA_HOME%"
rd /s /q "%ANDROID_HOME%"

rem 删除 Gradle 缓存（可选，下次构建会重新下载）
rd /s /q "%USERPROFILE%\.gradle"

rem 删除用户环境变量（用 setx 置空只会留下空值，删不干净）
reg delete "HKCU\Environment" /v JAVA_HOME /f
reg delete "HKCU\Environment" /v ANDROID_HOME /f
```

PATH 里的三条到 `sysdm.cpl` 的「用户变量 → Path」里删。

迁移到新机器：整体拷贝 `D:\Develop\SERVE\JAVA` 与 `D:\Develop\SERVE\Android`，
按第三步设好变量即可（两者都是绿色目录，不依赖安装器）。

---

## 附录 G：代理、内存与离线

在项目根目录或 `%USERPROFILE%\.gradle\gradle.properties` 中配置：

```properties
# 需要代理时
systemProp.http.proxyHost=127.0.0.1
systemProp.http.proxyPort=7890
systemProp.https.proxyHost=127.0.0.1
systemProp.https.proxyPort=7890

# 大项目内存与编码
org.gradle.jvmargs=-Xmx4g -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
```

- 依赖已全部下载后，可用 `gradlew.bat assembleDebug --offline` 完全离线构建；
- 换缓存盘：设置用户变量 `GRADLE_USER_HOME` 到新目录，再把原 `.gradle` 内容迁过去；
- 代理只影响 Gradle 自身；浏览器/IDE 的代理需要单独配置。
