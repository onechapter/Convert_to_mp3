import os
import subprocess
import browser_cookie3
from flask import Flask, render_template, request, send_from_directory
import re 
from unidecode import unidecode 
from urllib.parse import urlparse, parse_qs 

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

FFMPEG_LOCATION = "C:\\Program Files\\ffmpeg" 

# --- HÀM LẤY ID YOUTUBE ---
def get_youtube_id(url):
    if 'v=' in url:
        query = urlparse(url).query
        return parse_qs(query).get('v', [None])[0]
    elif 'youtu.be' in url:
        return urlparse(url).path[1:]
    return None


@app.route('/', methods=['GET', 'POST'])
def index():
    download_link = None
    error_message = None

    if request.method == 'POST':
        youtube_url = request.form.get('url')
        if not youtube_url:
            error_message = "Vui lòng nhập URL YouTube."
            return render_template('index.html', download_link=download_link, error_message=error_message)

        video_id = get_youtube_id(youtube_url)
        if not video_id:
             error_message = "URL YouTube không hợp lệ."
             return render_template('index.html', error_message=error_message)
             
        # Tên file sẽ bắt đầu bằng ID video để dễ dàng tìm kiếm
        output_template_raw = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{video_id}-%(title)s.%(ext)s") 
        COOKIE_FILE = os.path.join(app.root_path, 'cookies.txt')
        
        estimated_safe_name = None 
        error_message_temp = None

        # --- BẮT ĐẦU: LẤY VÀ GHI COOKIE VÀO TỆP ---
        try:
            cj = browser_cookie3.firefox(domain_name='youtube.com')
            found_yt_cookie = False
            
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
                
            with open(COOKIE_FILE, 'w') as f:
                f.write(f"# Netscape HTTP Cookie File\n") 
                for cookie in cj:
                    if 'youtube.com' in cookie.domain:
                        expires_value = str(cookie.expires) if cookie.expires is not None else '0'
                        # Fix lỗi: Đã sửa lại việc ghi expires_value
                        f.write(f"{cookie.domain}\tTRUE\t{cookie.path}\t{cookie.secure}\t{expires_value}\t{cookie.name}\t{cookie.value}\n") 
                        found_yt_cookie = True
            
            if not found_yt_cookie:
                 if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
                 error_message = "LỖI COOKIE: Không tìm thấy cookie. Hãy đảm bảo bạn đã ĐĂNG NHẬP YouTube trên Firefox và Firefox đã ĐÓNG hoàn toàn."
                 return render_template('index.html', error_message=error_message)

        except Exception as e:
            error_message = f"LỖI LẤY COOKIE: Vui lòng đóng Firefox. Lỗi chi tiết: {e}"
            return render_template('index.html', error_message=error_message)
        # ----------------------------------------


        # --- KIỂM TRA TỒN TẠI FILE (BẰNG CÁCH TÌM KIẾM THEO ID) ---
        found_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.startswith(f"{video_id}-") and f.endswith(".mp3")]

        if found_files:
            # Nếu tìm thấy, trả về file đầu tiên (chúng ta sẽ đổi tên nó ở đây)
            old_file_name = found_files[0]
            new_file_name = old_file_name.replace(f"{video_id}-", "", 1)
            
            old_path = os.path.join(app.config['DOWNLOAD_FOLDER'], old_file_name)
            new_path = os.path.join(app.config['DOWNLOAD_FOLDER'], new_file_name)

            if os.path.exists(old_path):
                # Đổi tên file
                os.rename(old_path, new_path)
                
            download_link = f"/download/{new_file_name}"
            if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
            return render_template('index.html', download_link=download_link, error_message="File đã tồn tại. Đây là liên kết tải xuống.")


        # --- BẮT ĐẦU QUÁ TRÌNH TẢI (Tải xuống và Phân tích Tên File) ---
        try:
            command = [
                'yt-dlp',
                '-x',                       
                '--audio-format', 'mp3',
                '-f', 'bestaudio',
                '--cookies', COOKIE_FILE,   
                '--ffmpeg-location', FFMPEG_LOCATION, 
                '--no-playlist',            
                '--output', output_template_raw, 
                '--sleep-requests', '1', 
                '--no-warnings', 
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', 
                youtube_url                 
            ]
            
            result = subprocess.run(command, check=True, capture_output=True) 
            
            
            # 3. PHÂN TÍCH LOG CỦA YT-DLP để lấy tên file chính xác
            old_file_name = None
            output_log = result.stdout.decode('utf-8', errors='ignore') + result.stderr.decode('utf-8', errors='ignore')
            
            # Regex tìm chuỗi báo cáo tên file: [download] Destination: downloads/ID-ten_file.mp3
            match = re.search(r'Destination: {}(.+?\.mp3)'.format(re.escape(DOWNLOAD_FOLDER + os.sep)), output_log)
            
            if match:
                old_file_name = match.group(1).strip()
            
            
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)

            if old_file_name and os.path.exists(os.path.join(app.config['DOWNLOAD_FOLDER'], old_file_name)):
                
                # --- THAO TÁC ĐỔI TÊN MỚI ---
                new_file_name = old_file_name.replace(f"{video_id}-", "", 1)
                
                old_path = os.path.join(app.config['DOWNLOAD_FOLDER'], old_file_name)
                new_path = os.path.join(app.config['DOWNLOAD_FOLDER'], new_file_name)
                
                try:
                    # Thực hiện đổi tên file
                    os.rename(old_path, new_path)
                    download_link = f"/download/{new_file_name}"
                except Exception as rename_error:
                    # Nếu đổi tên thất bại, vẫn trả về tên cũ và báo lỗi nhỏ
                    download_link = f"/download/{old_file_name}"
                    error_message = f"Cảnh báo: Đổi tên thất bại. Liên kết tải xuống sử dụng tên cũ (có ID). Lỗi: {rename_error}"
                # -----------------------------
                
            else:
                error_message = f"Tải xuống thành công nhưng không tìm thấy file MP3 cuối cùng."

        except subprocess.CalledProcessError as e:
            if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
            error_output = e.stderr.decode('utf-8', errors='ignore')
            if "HTTP Error 403: Forbidden" in error_output:
                 error_message = "LỖI TẢI XUỐNG: YouTube từ chối truy cập (403 Forbidden). Vui lòng kiểm tra lại cookie."
            else:
                 error_message = f"Lỗi Tải Xuống: {error_output}"
        
        except Exception as e:
            error_message = f"LỖI HỆ THỐNG: Lỗi chi tiết: {e}"
        
    return render_template('index.html', download_link=download_link, error_message=error_message)

# Route để phục vụ file đã tải (giữ nguyên)
@app.route('/download/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)