import os
import subprocess
import browser_cookie3
from flask import Flask, render_template, request, send_from_directory
import re 
from unidecode import unidecode 

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

FFMPEG_LOCATION = "C:\\Program Files\\ffmpeg" 

# --- HÀM CHUẨN HÓA TÊN FILE (Giữ nguyên) ---
def get_safe_filename(title):
    if not title:
        title = "unknown_video_title"
        
    safe_name = unidecode(title) 
    safe_name = re.sub(r'[\W_]+', '_', safe_name).strip('_')
    return f"{safe_name}.mp3"


@app.route('/', methods=['GET', 'POST'])
def index():
    download_link = None
    error_message = None

    if request.method == 'POST':
        youtube_url = request.form.get('url')
        if not youtube_url:
            error_message = "Vui lòng nhập URL YouTube."
            return render_template('index.html', download_link=download_link, error_message=error_message)

        output_template_raw = os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s.%(ext)s')
        COOKIE_FILE = os.path.join(app.root_path, 'cookies.txt')
        
        estimated_safe_name = None 
        video_title = None
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
                        f.write(f"{cookie.domain}\tTRUE\t{cookie.path}\t{cookie.secure}\t{expires_value}\t{cookie.name}\t{cookie.value}\n")
                        found_yt_cookie = True
            
            if not found_yt_cookie:
                 if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
                 error_message = "LỖI COOKIE: Không tìm thấy cookie. Hãy đảm bảo bạn đã ĐĂNG NHẬP YouTube trên Firefox và Firefox đã ĐÓNG hoàn toàn."
                 return render_template('index.html', error_message=error_message)

        except Exception as e:
            error_message = f"LỖI LẤY COOKIE: Vui lòng đóng Firefox. Lỗi chi tiết: {e}"
            return render_template('index.html', error_message=error_message)
        # --- KẾT THÚC: LẤY VÀ GHI COOKIE VÀO TỆP ---


        # --- KIỂM TRA TỒN TẠI FILE (Sử dụng cookie để có thể truy cập title) ---
        try:
            info_command = [
                'yt-dlp', 
                '--get-title', 
                '--no-playlist', 
                '--cookies', COOKIE_FILE, 
                youtube_url
            ]
            
            # SỬA LỖI GIẢI MÃ 1/2: Bỏ text=True và encoding
            title_result = subprocess.run(info_command, check=True, capture_output=True) 
            
            # Giải mã thủ công: dùng errors='ignore' để bỏ qua ký tự lỗi nếu cần
            if title_result.stdout:
                video_title = title_result.stdout.decode('utf-8', errors='ignore').strip()
            else:
                video_title = None
            
            if not video_title:
                 raise Exception("Không thể lấy tiêu đề video. Đang chuyển sang tải trực tiếp...")
            
            estimated_safe_name = get_safe_filename(video_title)
            estimated_safe_path = os.path.join(app.config['DOWNLOAD_FOLDER'], estimated_safe_name)

            if os.path.exists(estimated_safe_path):
                if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
                download_link = f"/download/{estimated_safe_name}"
                return render_template('index.html', download_link=download_link, error_message="File đã tồn tại. Đây là liên kết tải xuống.")
                
        except subprocess.CalledProcessError as e:
            # Nếu có lỗi, chúng ta cần cố gắng giải mã lỗi đó
            error_message_temp = f"Lỗi lấy thông tin: {e.stderr.decode('utf-8', errors='ignore')}"
        except Exception as e:
            error_message_temp = f"Lỗi hệ thống khi lấy thông tin: {e}"
        # --- KẾT THÚC KIỂM TRA TỒN TẠI FILE ---


        # --- BẮT ĐẦU QUÁ TRÌNH TẢI NẾU FILE CHƯA TỒN TẠI ---
        try:
            command = [
                'yt-dlp',
                '-x',                       
                '--audio-format', 'mp3',
                '-f', 'bestaudio',
                '--cookies', COOKIE_FILE,   
                '--ffmpeg-location', FFMPEG_LOCATION, 
                '--no-playlist',            
                '--restrict-filenames',     
                '--output', output_template_raw,
                '--sleep-requests', '1', 
                '--no-warnings', 
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', 
                youtube_url                 
            ]
            
            # SỬA LỖI GIẢI MÃ 2/2: Bỏ text=True và encoding
            result = subprocess.run(command, check=True, capture_output=True) 
            
            # 3. XỬ LÝ KẾT QUẢ VÀ DỌN DẸP
            if not estimated_safe_name:
                # Nếu không lấy được tên, thử lấy lại lần cuối
                info_command = ['yt-dlp', '--get-title', '--no-playlist', '--cookies', COOKIE_FILE, youtube_url]
                title_result = subprocess.run(info_command, check=True, capture_output=True)
                video_title = title_result.stdout.decode('utf-8', errors='ignore').strip() if title_result.stdout else None
                if not video_title:
                     # Nếu vẫn không lấy được, đặt tên mặc định để không crash
                     estimated_safe_name = get_safe_filename(None) 
                else:
                    estimated_safe_name = get_safe_filename(video_title)

            final_file = estimated_safe_name 
            
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)

            if estimated_safe_name and os.path.exists(os.path.join(app.config['DOWNLOAD_FOLDER'], estimated_safe_name)):
                download_link = f"/download/{estimated_safe_name}"
            else:
                error_message = f"Tải xuống thành công nhưng không tìm thấy file MP3 cuối cùng."

        except subprocess.CalledProcessError as e:
            if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
            # SỬA LỖI: Giải mã lỗi thủ công
            error_output = e.stderr.decode('utf-8', errors='ignore')
            if "HTTP Error 403: Forbidden" in error_output:
                 error_message = "LỖI TẢI XUỐNG: YouTube từ chối truy cập (403 Forbidden). Vui lòng kiểm tra lại cookie của Firefox (đã đăng nhập) và đóng Firefox."
            else:
                 error_message = f"Lỗi Tải Xuống: {error_output}"
        
        except Exception as e:
            error_message = f"LỖI HỆ THỐNG: Lỗi chi tiết: {e}"
        
        if not error_message and error_message_temp:
             error_message = error_message_temp

    return render_template('index.html', download_link=download_link, error_message=error_message)

# Route để phục vụ file đã tải (giữ nguyên)
@app.route('/download/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)