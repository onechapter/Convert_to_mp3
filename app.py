import os
import subprocess
import browser_cookie3
from flask import Flask, render_template, request, send_from_directory
import re 
from unidecode import unidecode 

app = Flask(__name__)
# Đặt thư mục để lưu trữ file tải xuống.
DOWNLOAD_FOLDER = 'downloads'
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

# Tạo thư mục downloads nếu nó chưa tồn tại
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Cấu hình FFmpeg 
# HÃY CHẮC CHẮN ĐƯỜNG DẪN NÀY LÀ CHÍNH XÁC (thường là thư mục 'bin' của FFmpeg)!
FFMPEG_LOCATION = "C:\\Program Files\\ffmpeg" 

# --- HÀM CHUẨN HÓA TÊN FILE THỦ CÔNG (Dùng để ước tính tên file đã tải) ---
# Hàm này mô phỏng cách YT-DLP sử dụng --restrict-filenames
def get_safe_filename(title):
    if not title:
        title = "unknown_video_title"
        
    # 1. Bỏ dấu tiếng Việt và chuyển sang Latin (Lặng Yên -> Lang Yen)
    safe_name = unidecode(title) 
    # 2. Thay thế mọi thứ không phải chữ cái, số, gạch dưới hoặc dấu chấm bằng dấu gạch dưới (Lang Yen -> Lang_Yen)
    safe_name = re.sub(r'[\W_]+', '_', safe_name).strip('_')
    # 3. Thêm đuôi .mp3
    return f"{safe_name}.mp3"


@app.route('/', methods=['GET', 'POST'])
def index():
    download_link = None
    error_message = None

    if request.method == 'POST':
        youtube_url = request.form.get('url')
        
        # ⚠️ Kiểm tra URL đầu vào
        if not youtube_url:
            error_message = "Vui lòng nhập URL YouTube."
            return render_template('index.html', download_link=download_link, error_message=error_message)

        # Định nghĩa biến
        output_template_raw = os.path.join(app.config['DOWNLOAD_FOLDER'], '%(title)s.%(ext)s')
        COOKIE_FILE = os.path.join(app.root_path, 'cookies.txt')
        
        # KHỞI TẠO BIẾN TRƯỚC KHỐI TRY ĐỂ TRÁNH LỖI PHẠM VI
        estimated_safe_name = None 
        video_title = None
        error_message_temp = None

        # --- KIỂM TRA TỒN TẠI FILE TRƯỚC KHI TẢI ---
        try:
            # Lấy thông tin video (tiêu đề) mà không tải
            info_command = ['yt-dlp', '--get-title', '--no-playlist', youtube_url]
            title_result = subprocess.run(info_command, check=True, capture_output=True, text=True, encoding='utf-8')
            
            # Xử lý lỗi NoneType: Kiểm tra .stdout trước khi gọi .strip()
            video_title = title_result.stdout.strip() if title_result.stdout else None
            
            if not video_title:
                 raise Exception("Không thể lấy tiêu đề video (có thể do lỗi 403 hoặc URL không hợp lệ). Đang chuyển sang tải trực tiếp...")
            
            # Ước tính tên file đã được chuẩn hóa
            estimated_safe_name = get_safe_filename(video_title)
            estimated_safe_path = os.path.join(app.config['DOWNLOAD_FOLDER'], estimated_safe_name)

            # KIỂM TRA: Nếu file tên an toàn đã tồn tại, TRẢ VỀ LINK DOWNLOAD NGAY
            if os.path.exists(estimated_safe_path):
                download_link = f"/download/{estimated_safe_name}"
                return render_template('index.html', download_link=download_link, error_message="File đã tồn tại. Đây là liên kết tải xuống.")
                
        except subprocess.CalledProcessError as e:
            error_message_temp = f"Lỗi lấy thông tin: {e.stderr}"
        except Exception as e:
            error_message_temp = f"Lỗi hệ thống khi lấy thông tin: {e}"
        # --- KẾT THÚC KIỂM TRA TỒN TẠI FILE ---


        # --- BẮT ĐẦU QUÁ TRÌNH TẢI NẾU FILE CHƯA TỒN TẠI ---
        try:
            # 1. LẤY VÀ LƯU COOKIE TỰ ĐỘNG TỪ FIREFOX
            cj = browser_cookie3.firefox(domain_name='youtube.com')
            found_yt_cookie = False
            with open(COOKIE_FILE, 'w') as f:
                f.write(f"# Netscape HTTP Cookie File\n") 
                for cookie in cj:
                    if 'youtube.com' in cookie.domain:
                        # SỬA LỖI: Chuyển None thành '0' để tránh lỗi YT-DLP Warning/403
                        expires_value = str(cookie.expires) if cookie.expires is not None else '0'
                        
                        f.write(f"{cookie.domain}\tTRUE\t{cookie.path}\t{cookie.secure}\t{expires_value}\t{cookie.name}\t{cookie.value}\n")
                        found_yt_cookie = True
            
            if not found_yt_cookie:
                 if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
                 error_message = "LỖI COOKIE: Vui lòng đảm bảo bạn đã ĐĂNG NHẬP YouTube trên Firefox và Firefox đã ĐÓNG hoàn toàn."
                 return render_template('index.html', error_message=error_message)


            # 2. XÂY DỰNG VÀ CHẠY LỆNH YT-DLP
            command = [
                'yt-dlp',
                '-x',                       
                '--audio-format', 'mp3',
                '-f', 'bestaudio',
                '--cookies', COOKIE_FILE,   
                '--ffmpeg-location', FFMPEG_LOCATION, 
                '--no-playlist',            
                '--restrict-filenames',     # Sử dụng tùy chọn này để yt-dlp tự tạo tên an toàn
                '--output', output_template_raw,
                youtube_url                 
            ]
            
            result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
            
            # 3. XỬ LÝ KẾT QUẢ VÀ DỌN DẸP
            
            # Nếu khối try đầu tiên thất bại, chúng ta phải lấy lại tiêu đề ở đây
            if not estimated_safe_name:
                info_command = ['yt-dlp', '--get-title', '--no-playlist', youtube_url]
                title_result = subprocess.run(info_command, check=True, capture_output=True, text=True, encoding='utf-8')
                video_title = title_result.stdout.strip() if title_result.stdout else None
                if not video_title:
                     raise Exception("Tải xuống thành công nhưng không thể lấy tiêu đề cho link download.")
                estimated_safe_name = get_safe_filename(video_title)

            final_file = estimated_safe_name 
            
            # Dọn dẹp tệp cookie sau khi sử dụng thành công
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)

            if final_file and os.path.exists(os.path.join(app.config['DOWNLOAD_FOLDER'], final_file)):
                download_link = f"/download/{final_file}"
            else:
                error_message = f"Tải xuống thành công nhưng không tìm thấy file MP3 cuối cùng."

        except subprocess.CalledProcessError as e:
            if os.path.exists(COOKIE_FILE): os.remove(COOKIE_FILE)
            error_message = f"Lỗi Tải Xuống: {e.stderr}"
        
        except Exception as e:
            error_message = f"LỖI HỆ THỐNG: Lỗi chi tiết: {e}"
        
        # Nếu có lỗi tạm thời (ví dụ: không lấy được title nhưng vẫn tiếp tục tải)
        if not error_message and error_message_temp:
             error_message = error_message_temp

    return render_template('index.html', download_link=download_link, error_message=error_message)

# Route để phục vụ file đã tải (giữ nguyên)
@app.route('/download/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)