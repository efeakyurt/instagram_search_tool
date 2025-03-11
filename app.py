from flask import Flask, render_template, request, make_response
from instaloader import Instaloader, Profile
from instaloader.exceptions import (
    ProfileNotExistsException, 
    PrivateProfileNotFollowedException,
    BadCredentialsException,
    ConnectionException,
    InvalidArgumentException
)
import re
import os
from time import sleep
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def create_loader():
    return Instaloader(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        sleep=True,
        quiet=True,
        request_timeout=30
    )

def validate_form_data(data):
    required_fields = ['ig_username', 'ig_password', 'target_account', 'username_search']
    for field in required_fields:
        if not data.get(field, '').strip():
            raise ValueError(f"{field.replace('_', ' ').title()} boş bırakılamaz!")
    return True

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    last_search = request.cookies.get('last_search', '')
    L = create_loader()
    
    if request.method == 'POST':
        try:
            # Form verilerini güvenli şekilde al
            form_data = {
                'ig_username': request.form.get('ig_username', '').strip(),
                'ig_password': request.form.get('ig_password', ''),
                'target_account': request.form.get('target_account', '').strip().lstrip('@'),
                'username_search': request.form.get('username_search', '').strip(),
                'bio_search': request.form.get('bio_search', '').strip()
            }
            
            # Validasyon
            validate_form_data(form_data)
            
            # Oturum yönetimi
            session_file = f"./session_{form_data['ig_username']}"
            if os.path.exists(session_file):
                try:
                    L.load_session_from_file(form_data['ig_username'], filename=session_file)
                except InvalidArgumentException:
                    os.remove(session_file)
                    raise

            if not L.context.is_logged_in:
                L.login(
                    user=form_data['ig_username'],
                    passwd=form_data['ig_password']
                )
                L.save_session_to_file(filename=session_file)

            # Profil verilerini çek
            profile = Profile.from_username(L.context, form_data['target_account'])
            
            # Takipçi listesi
            followers = profile.get_followers()
            
            # Arama parametreleri
            username_pattern = re.compile(re.escape(form_data['username_search']), re.IGNORECASE)
            bio_pattern = re.compile(re.escape(form_data['bio_search']), re.IGNORECASE) if form_data['bio_search'] else None
            
            results = []
            start_time = datetime.now()
            
            for count, follower in enumerate(followers, 1):
                if (datetime.now() - start_time).total_seconds() > 300:
                    break
                
                if count % 15 == 0:
                    sleep(25)
                elif count % 5 == 0:
                    sleep(10)
                
                if not username_pattern.search(follower.username):
                    continue
                    
                if bio_pattern and not bio_pattern.search(follower.biography or ''):
                    continue
                
                results.append({
                    'username': follower.username,
                    'full_name': follower.full_name or '-',
                    'bio': (follower.biography or '-')[:150] + '...' if len(follower.biography or '') > 150 else follower.biography,
                    'followers': f"{follower.followers:,}",
                    'followees': f"{follower.followees:,}",
                    'profile_pic': follower.profile_pic_url,
                    'is_private': 'Evet' if follower.is_private else 'Hayır'
                })
                
                if len(results) >= 75:
                    break

            response = make_response(render_template(
                'results.html',
                results=results,
                search_params={
                    'target_account': f"@{form_data['target_account']}",
                    'username_search': form_data['username_search'],
                    'bio_search': form_data['bio_search']
                }
            ))
            response.set_cookie('last_search', form_data['target_account'], max_age=60*60*24*7, httponly=True, samesite='Lax')
            return response

        except ValueError as ve:
            error = str(ve)
        except (BadCredentialsException, InvalidArgumentException):
            error = "Geçersiz kullanıcı adı veya şifre!"
        except ProfileNotExistsException:
            error = "Hedef hesap bulunamadı!"
        except PrivateProfileNotFollowedException:
            error = "Gizli hesap - Takip etmiyorsunuz!"
        except ConnectionException:
            error = "İnternet bağlantı hatası!"
        except Exception as e:
            error = f"Beklenmeyen hata: {type(e).__name__}"
        finally:
            L.close()

    return render_template('index.html', error=error, last_search=last_search)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)