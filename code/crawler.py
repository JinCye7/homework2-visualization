import os
import json
import time
import random
import logging
import pandas as pd
import requests
from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
print("★★★ 文件将会被保存在这个文件夹里：", os.getcwd())
# ==========================================
# 模块一：工业级日志监控与链路追踪初始化
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [NetEase Crawler] - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# ==========================================
# 模块二：WeAPI混合密码学逆向引擎
# ==========================================
class NeteaseCryptoEngine:
    def __init__(self):
        # 预置系统级公钥参数与固定随机量
        self.modulus = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
        self.nonce = "0CoJUm6Qyw8W8jud"
        self.pubKey = "010001"
        self.iv = "0102030405060708"

    def _create_secret_key(self, size=16):
        chars = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        return ''.join(random.choice(chars) for _ in range(size))

    def _aes_encrypt(self, text, key):
        pad = 16 - len(text) % 16
        text = text + pad * chr(pad)
        encryptor = AES.new(key.encode('utf-8'), AES.MODE_CBC, self.iv.encode('utf-8'))
        ciphertext = encryptor.encrypt(text.encode('utf-8'))
        return b64encode(ciphertext).decode('utf-8')

    def _rsa_encrypt(self, text):
        text = text[::-1]
        rs = int(text.encode('utf-8').hex(), 16) ** int(self.pubKey, 16) % int(self.modulus, 16)
        return format(rs, 'x').zfill(256)

    def generate_payload(self, raw_data_dict):
        text = json.dumps(raw_data_dict)
        secret_key = self._create_secret_key(16)
        params_intermediate = self._aes_encrypt(text, self.nonce)
        params_final = self._aes_encrypt(params_intermediate, secret_key)
        encSecKey = self._rsa_encrypt(secret_key)
        return {'params': params_final, 'encSecKey': encSecKey}

# ==========================================
# 模块三：基于多维特征提取的主控爬虫状态机
# ==========================================
class CommentCrawlerStateMachine:
    def __init__(self, target_song_id, max_comments=100000):
        self.song_id = target_song_id
        self.target_count = max_comments
        self.api_endpoint = "https://music.163.com/weapi/comment/resource/comments/get?csrf_token="
        self.crypto = NeteaseCryptoEngine()
        
        self.session = requests.Session()
        
        # 严格遵守防盗链伪装规范
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Origin': 'https://music.163.com',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Content-Type': 'application/x-www-form-urlencoded',
            # [重要] 依然需要填入你的真实有效 Cookie
            'Cookie': 'P_INFO=13868595470|1767759157|1|phoenix_client|00&99|null&null&null#zhj&330100#10#0|&0||13868595470; _iuqxldmzr_=32; _ntes_nnid=a890d56524be582e62899d153a4e6ad1,1778854991012; _ntes_nuid=a890d56524be582e62899d153a4e6ad1; NMTID=00OyzvVKeIL9uEYeU_vgFak3OwJP_AAAAGeLAUTPw; WEVNSM=1.0.0; WNMCID=tkjokp.1778854991880.01.0; WM_NI=wV2nhfE7DZUvyZ4STI%2FN8qSBhbO1PIQwkK4jTp5otsGDYop0eP5DeFgfxQsub3h%2Fm%2FgJX6fxEG%2FqoXSrw2wIyDlBnB%2FrQ0JmOFu86qACaR1OYdN9Tx0DudHEICQLUZsFNlE%3D; WM_NIKE=9ca17ae2e6ffcda170e2e6ee8feb5fa9ba8dd6cf4ea9968aa3d54b828a9a87c67f83b6b9b2c74398a9feaee22af0fea7c3b92ab58afe8feb6e87e98cbbd87ebb86fcb4d743ed92f892d24aacbe81d2d34393a9a5acb76298b0fb90f779859c9790f33ca790fba5e84ea5bab8b2f27fa2eda8d0f025a59698d7e5748799e192ee5491aeb9d3f643bb9ca4a3ed4aedae9fd1c9678d9abbd9b57b839dafb3b4459bbc82dad774f49cbb85cb4f8b9d9fadd852b19a828dc837e2a3; WM_TID=q97aidp2tlZEEVBRFFbTrRnhFCJHxiMZ; sDeviceId=YD-yi2NlzgSfW9FQ0VUVAbG%2FUywVHZDhc66; __snaker__id=N9cB1GwjFPzYJOxe; ntes_utid=tid._.118nvGVKSDhBE1UBQAfD%252BAjlVGMChcqr._.0; gdxidpyhxdE=k%2F0g7wc4Kn4POyabovrlB3MajqITQi3kdktnL%2BBCIy709lPCSLNMVbu7vbuOZ9%5CMIU3oZd87rODxzO3cmu5yE5n6YGCHyyjVUonHvZiW82XXaE%2Bdr5gpvxuSZS0GTTfQSYinZJP5kk2zAZI2rNEUH7qGRN%2BNzZQhcTXgDk3Yp2VjyqUB%3A1778856028331; MUSIC_U=00785B06CFC0D3045D04EC3B0224662D7E8A6EB9F7D98DF04287F3E0F4DEF8E8DD58B38E89BCD7DBEE018EB2A8A1CA127C9E88ACC48D3C37149147F52AEEBB6025DD7A2046BC0B59DE17740689C42E53FCAB17280BC9F39CA6F158E83546DFCD6DA24BC4A3996D44606D4BBDC54DB0504052E1D7986C290F5CC6307E081AD31F7A9C64BD51116682944B8E5A41699DF9C4F524F476DD7BDEF224CF84017F5456A4796163CB3BF983B49651ADDA28FB995034A44A330273B360485F86E2F63C7441EDE2F3EA2B9E75285A0C23B3794E5A370180491806EDBEB2875C34A9F05FEE03A74D91413958A4B5AE75450B8C892334596DCDC9EB4BE42B6EE0038B26F6AAC5A74648B603917FA2DA7CB740BD49196ABE4DD768C2D9680E2EEDB646DCD44A564BDB263E53A0F8ED5505A38AE3D23069D199263B139F4F31A6C43FF33A3315A8A712D9AF9A433A670A278B42D6D613FE97E4D38DFF55ADDC0E4143F496E1D1F031B8E4AFAE26079A7C177FFE05C310060B79DCF0E53D0584559608AC92460897DC6E7EFA4CC9D1E5A2CCD6596B54691A7BC8BF2F377EE0D34DAAB702CF86CE25; __csrf=f8635d4c6604c0fbd9466097020534e3; ntes_kaola_ad=1; Hm_lvt_1483fb4774c02a30ffa6f0e2945e9b70=1778854991,1778855561; Hm_lpvt_1483fb4774c02a30ffa6f0e2945e9b70=1778855561; HMACCOUNT=333924D584A846F2; JSESSIONID-WYYY=xTqFvbvCBtqz2W%2BaRe1lxmJUSy3FDgl3T%5Ck0b0jGf9YCXwBf4pCdRPgiKaBqSBUDCqdhg0NCUvlxln5RSpFhH6gsDMYQ2JFe%2BgsWnSWsc5H%2Fy0Tp7%5CE0MUR4TN36D3%5CWbZ%2FYcg10cEtSS77FgFWT4S0P70767rD%2Bioc0%2Fra0YG3%5C6J8T%3A1778860272484' 
        })
        
        self.hot_comment_buffer = []    
        self.normal_comment_buffer = [] 
        self.cursor = "-1"
        self.page_index = 1
        
    def _execute_network_request(self):
        # [修改点] 将 pageSize 改为了 10
        payload = {
            "csrf_token": "",
            "cursor": str(self.cursor),
            "offset": "0",
            "orderType": "1",
            "pageNo": str(self.page_index),
            "pageSize": "10", 
            "rid": f"R_SO_4_{self.song_id}",
            "threadId": f"R_SO_4_{self.song_id}"
        }
        
        encrypted_form_data = self.crypto.generate_payload(payload)
        
        try:
            response = self.session.post(self.api_endpoint, data=encrypted_form_data, timeout=15)
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    logging.error(f"解析JSON失败，可能是触发风控验证码。")
                    return None
            else:
                logging.error(f"遭遇异常HTTP状态码: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"网络请求异常: {e}")
            return None

    def _clean_text(self, raw_text):
        if not raw_text:
            return ""
        return raw_text.replace('\n', ' ').replace('\r', ' ').replace(',', '，')

    def _extract_comment_features(self, item, category):
        """核心数据提取单元：解析嵌套JSON，扁平化为多维特征"""
        user_info = item.get('user', {})
        ip_info = item.get('ipLocation', {}) 
        be_replied = item.get('beReplied', [])

        # 解析楼中楼（被回复者）信息
        replied_user_id = ''
        replied_content = ''
        if be_replied and len(be_replied) > 0:
            replied_user_id = be_replied[0].get('user', {}).get('userId', '')
            replied_content = self._clean_text(be_replied[0].get('content', ''))

        return {
            'Comment_ID': item.get('commentId'),
            'Category_Label': category,
            
            # 文本与互动特征
            'Content': self._clean_text(item.get('content')),
            'Liked_Count': item.get('likedCount', 0),
            'Reply_Count': item.get('replyCount', 0),
            'Text_Length': len(item.get('content', '')),
            
            # 时间特征 (保留原始13位时间戳，方便后续转换)
            'Timestamp': item.get('time', 0), 
            'Time_String': item.get('timeStr', ''), # 接口若直接返回格式化时间则保存
            
            # 用户画像特征
            'User_ID': user_info.get('userId', ''),
            'Nickname': self._clean_text(user_info.get('nickname', '')),
            'VIP_Type': user_info.get('vipType', 0),
            'Auth_Status': user_info.get('authStatus', 0),
            
            # 地理空间特征
            'IP_Location': ip_info.get('location', '未知') if ip_info else '未知',
            
            # 社交拓扑网络特征
            'Is_Nested_Reply': 1 if be_replied else 0, 
            'Replied_User_ID': replied_user_id,
            'Replied_Content': replied_content
        }

    def start_harvesting(self):
        logging.info(f"爬虫引擎启动，目标：{self.target_count} 条数据，每页请求 10 条。")
        
        while len(self.normal_comment_buffer) < self.target_count:
            json_response = self._execute_network_request()
            
            if not json_response or json_response.get('code') != 200:
                logging.warning("请求异常或触发频控，休眠60秒退避...")
                time.sleep(60)
                continue
                
            data_container = json_response.get('data', {})
            
            # 仅首屏抓取热门评论
            if self.page_index == 1 and 'hotComments' in data_container:
                for item in data_container['hotComments'][:15]:
                    self.hot_comment_buffer.append(
                        self._extract_comment_features(item, 'Hot_Comment')
                    )
                logging.info("首屏热门评论解析完毕。")

            comments_array = data_container.get('comments', []) 
            if not comments_array:
                logging.info("服务端返回空数组，已到达评论区底部，提前终止。")
                break
                
            # 解析普通评论
            for item in comments_array:
                self.normal_comment_buffer.append(
                    self._extract_comment_features(item, 'Normal_Comment')
                )
                
                if len(self.normal_comment_buffer) >= self.target_count:
                    break
                    
            current_total = len(self.normal_comment_buffer)
            logging.info(f"第 {self.page_index} 页抓取完成，当前主库水位线：{current_total} 条")
            
            self.cursor = data_container.get('cursor', self.cursor)
            self.page_index += 1
            
            # 时序拟态防封（由于单页数据量变小，请求会变密集，适当增加休眠基数）
            mimicry_delay = random.uniform(1.8, 3.5)
            time.sleep(mimicry_delay)
            
            # 每采集 10000 条进行一次灾备落盘
            if current_total % 10000 == 0 and current_total > 0:
                self.dump_to_storage(is_checkpoint=True)

        self.dump_to_storage(is_checkpoint=False)
        logging.info(f"任务圆满结束。共采集 {len(self.normal_comment_buffer)} 条普通评论。")

    def dump_to_storage(self, is_checkpoint=False):
        aggregated_data = self.hot_comment_buffer + self.normal_comment_buffer
        dataframe = pd.DataFrame(aggregated_data)
        
        file_suffix = "checkpoint" if is_checkpoint else "final"
        filename = f"netease_comments_{self.song_id}_{file_suffix}.csv"
        absolute_path = os.path.join(os.getcwd(), filename)
        
        dataframe.to_csv(absolute_path, index=False, encoding='utf-8-sig')
        logging.info(f"数据集群已成功序列化至磁盘：{absolute_path}")

# ==========================================
# 模块四：系统执行引导进程
# ==========================================
if __name__ == "__main__":
    # 目标歌曲ID保持不变
    TARGET_IDENTIFIER = "1890530891" 
    # [修改点] 将目标量改为 10 万条
    DESIRED_VOLUME = 100000
    
    spider_engine = CommentCrawlerStateMachine(
        target_song_id=TARGET_IDENTIFIER, 
        max_comments=DESIRED_VOLUME
    )
    spider_engine.start_harvesting()