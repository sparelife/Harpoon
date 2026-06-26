# -*- coding: utf-8 -*-



import akshare as ak
import numpy as np
import pandas as pd
import math
import datetime
import os
import matplotlib.pyplot as plt
import openpyxl
import re
import pickle
import json
import requests

pd.set_option('display.max_rows',None)
pd.set_option('display.max_columns',None)
pd.set_option('display.width',1000)
import matplotlib
matplotlib.use('Agg')

# ── 集思录登录 ──────────────────────────────────────────
JISILU_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jisilu_config.json')
JISILU_COOKIE_FILE = os.path.expanduser('~/.jisilu_cookies.pkl')

def jisilu_encode(text, aes_key):
    """AES-128-ECB 加密，PKCS7 填充，输出 hex（与集思录前端 CryptoJS 一致）"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    key = aes_key.encode('utf-8')
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    data = text.encode('utf-8')
    pad_len = 16 - len(data) % 16
    padded = data + bytes([pad_len] * pad_len)
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return encrypted.hex()

def load_jisilu_config():
    """读取 ~/.jisilu_config.json，返回 (username, password, filter_dict)"""
    if not os.path.exists(JISILU_CONFIG):
        print("错误：未找到配置文件 %s" % JISILU_CONFIG)
        print("请创建该文件，内容示例：")
        print('  {"username": "手机号", "password": "密码", "filter": {...}}')
        exit(1)
    try:
        with open(JISILU_CONFIG) as f:
            cfg = json.load(f)
        username = cfg['username']
        password = cfg['password']
        flt = cfg.get('filter', {})
        return username, password, flt
    except Exception as e:
        print("错误：配置文件格式不正确：%s" % e)
        exit(1)

def jisilu_login(username, password):
    """集思录用户名密码登录，返回带 cookies 的 Session"""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://www.jisilu.cn',
        'Referer': 'https://www.jisilu.cn/login/',
        'X-Requested-With': 'XMLHttpRequest',
    })
    # 获取登录页，取 AES key
    r = s.get('https://www.jisilu.cn/login/', timeout=15)
    key_match = re.search(r"var key\s*=\s*[\"']([^\"']*)[\"']", r.text)
    if not key_match:
        print('错误：无法从登录页获取 AES key')
        return None
    aes_key = key_match.group(1)
    # 加密后 POST 登录
    login_data = {
        'return_url': '/',
        'user_name': jisilu_encode(username, aes_key),
        'password': jisilu_encode(password, aes_key),
        'aes': '1',
        'auto_login': '1',
    }
    r2 = s.post('https://www.jisilu.cn/webapi/account/login_process/',
                data=login_data, timeout=15)
    try:
        result = r2.json()
    except Exception:
        print('登录失败：服务器返回异常')
        return None
    if result.get('code') == 200:
        print('集思录登录成功')
        os.makedirs(os.path.dirname(JISILU_COOKIE_FILE) or '.', exist_ok=True)
        with open(JISILU_COOKIE_FILE, 'wb') as f:
            pickle.dump(dict(s.cookies), f)
        return s
    else:
        msg = result.get('msg', '未知错误')
        print('集思录登录失败：%s' % msg)
        if result.get('data', {}).get('captcha'):
            print('提示：触发验证码，登录环境变更后重试')
        return None

def ensure_jisilu_session():
    """返回有效 Session：优先用缓存，失效则重新登录"""
    # 尝试缓存
    if os.path.exists(JISILU_COOKIE_FILE):
        try:
            with open(JISILU_COOKIE_FILE, 'rb') as f:
                cookies = pickle.load(f)
            s = requests.Session()
            s.cookies.update(cookies)
            s.headers.update({'User-Agent': 'Mozilla/5.0'})
            r = s.get('https://www.jisilu.cn/', timeout=10)
            if r.status_code == 200:
                print('使用缓存的登录状态')
                return s
        except Exception:
            pass
    # 重新登录
    username, password, _ = load_jisilu_config()
    sess = jisilu_login(username, password)
    return sess

def cookie_from_session(sess):
    """从 Session 提取 cookie 字符串供 akshare 使用"""
    return '; '.join('%s=%s' % (k, v) for k, v in sess.cookies.items())


def get_akshare_jsl(xlsfile,cookie):
    shname = 'jsl'
    isExist = os.path.exists(xlsfile)
    if not isExist:
        bond_convert_jsl_df = ak.bond_cb_jsl(cookie)
        bond_convert_jsl_df.to_excel(xlsfile, sheet_name=shname)

        print("xfsfile:%s create" % (xlsfile))
    else:
        print("xfsfile:%s exist" % (xlsfile))

    return xlsfile, shname

def calc_value_center():
	stock_premium = [0.81,0,-0.1,-5.56,-3,8.34,0.28,-5.2,-8.24,2.34,-7.3,-26.52,-0.29]
	debt_premium =  [-2.79,0.79,2.09,2.58,2.89,4.63,5.18,7.33,7.4,7.44,7.46,9.23,9.52]
	return np.mean(stock_premium),np.mean(debt_premium)


def calc_mahalanobis_inv():
    """根据理想样本计算 2×2 协方差逆矩阵（马氏距离用）"""
    stock_premium = np.array([0.81, 0, -0.1, -5.56, -3, 8.34, 0.28, -5.2, -8.24, 2.34, -7.3, -26.52, -0.29])
    debt_premium  = np.array([-2.79, 0.79, 2.09, 2.58, 2.89, 4.63, 5.18, 7.33, 7.4, 7.44, 7.46, 9.23, 9.52])
    data = np.vstack([stock_premium, debt_premium]).T  # (13, 2)
    cov = np.cov(data, rowvar=False)                     # 2×2
    return np.linalg.inv(cov)


def calc_value_distance(a, b, va, vb, cov_inv):
    """马氏距离：sqrt(diffᵀ · Σ⁻¹ · diff)"""
    diff = np.array([a - va, b - vb])
    return math.sqrt(diff @ cov_inv @ diff)

def calc_bond_value(price,ratio,year):
    if ratio == '':
        return 130
    else:
        #ratio = float(ratio.strip('%'))/100
        ratio = float(ratio)/100
        govload = 0.04
        
        if ratio <= -1:
        	return 100
        else:
        	return price*(1+ratio)**year/(1+govload)**year

def calc_interest_value(price,ratio,year):
    if ratio == '':
        return 130
    else:
        #ratio = float(ratio.strip('%'))/100
        ratio = float(ratio)/100
        return (price*(1+ratio)**year).real

def calc_bond_overflow(price,bondvalue):
    return 100 * (price - bondvalue) / bondvalue

def calc_stock_overflow(overflow):
    #return float(overflow.strip('%'))
    return float(overflow)
    
def calc_new_code(code):
    newcode = ''
    codefind = re.findall(pattern='^(127|128|123).*?',string=code)
    #print(codefind)
    if len(codefind)>0:
      newcode = 'sz' + code
    else:
      newcode = 'sh' + code
    #print(newcode)
    return newcode    

def get_pass_days(date):
	if date == '-':
		return -99
	else:
		delt = datetime.datetime.now() - datetime.datetime.strptime(date, '%Y%m%d')
		return delt.days

def apply_filter(df, filters):
    """根据配置的过滤条件筛选 DataFrame，跳过不存在的字段"""
    mask = pd.Series(True, index=df.index)

    limit_map = {
        '剩余规模上限': ('剩余规模', 'upper'),
        '现价上限':     ('现价',     'upper'),
        '剩余年限上限': ('剩余年限', 'upper'),
        '剩余年限下限': ('剩余年限', 'lower'),
    }
    for cfg_key, (col, bound) in limit_map.items():
        val = filters.get(cfg_key)
        if val is not None and col in df.columns:
            if bound == 'upper':
                mask &= df[col] <= val
            else:
                mask &= df[col] >= val

    # 评级前缀过滤
    rating_prefix = filters.get('评级前缀')
    if rating_prefix is not None and '债券评级' in df.columns:
        pattern = '^' + re.escape(str(rating_prefix))
        mask &= df['债券评级'].str.contains(pattern, na=False)

    return df[mask].copy()


def select_kgood_some(writer, bond_expect_df, tag, filters):
    """按配置过滤、排序、输出转债"""
    try:
      print("过滤条件: " + json.dumps(filters, ensure_ascii=False))
      bond_expect_kgood_df = apply_filter(bond_expect_df, filters)
      bond_expect_kgood_df = bond_expect_kgood_df.sort_values('到期税前收益', ascending=False)
      bond_expect_kgood_df.to_excel(writer, sheet_name=tag)
      bond_expect_kgood_df['代码'] = bond_expect_kgood_df.apply(lambda row: calc_new_code(str(row['代码'])), axis=1)
      return bond_expect_kgood_df[['代码','转债名称','剩余规模','含息价','剩余年限']]
    except Exception as result:
      print(result)
      bond_expect_kgood_df = pd.DataFrame(columns=['代码', '转债名称','剩余规模','含息价','剩余年限'])
      return bond_expect_kgood_df


if __name__=='__main__':

    from sys import argv
    tnow = datetime.datetime.now()
    show_help = False

    args = argv[1:]
    if '--help' in args or '-h' in args:
        show_help = True
    else:
        # 只接受 [日期] 一个可选参数
        if len(args) >= 1 and args[0] != '*':
            try:
                tnow = datetime.datetime.strptime(args[0], '%Y-%m-%d')
            except ValueError:
                show_help = True
        if len(args) >= 2:
            show_help = True

    if show_help:
        print("用法:  python harpoon.py [日期]")
        print()
        print("  [日期]     不填            今天（默认）")
        print("             2026-06-18    指定日期")
        print()
        print("  过滤条件在 jisilu_config.json（同目录）中配置：")
        print('    "剩余规模上限": 5.0')
        print('    "现价上限":     121.0')
        print('    "剩余年限上限": 5')
        print('    "剩余年限下限": 1.5')
        print('    "评级前缀":     "A"')
        print("  缺省字段表示不限制。")
        print()
        print("  示例:")
        print("    python harpoon.py")
        print("    python harpoon.py 2026-06-18")
        exit(1)

    # ── 自动登录集思录 ──
    sess = ensure_jisilu_session()
    if sess is None:
        exit(1)
    cookie = cookie_from_session(sess)

    print("time is :" + tnow.strftime('%Y%m%d'))

    filefolder = r'./data/' + tnow.strftime('%Y%m%d')
    filein = tnow.strftime('%Y_%m_%d') + '_in.xlsx'
    getakpath =  "%s/%s" % (filefolder,filein)

    isExist = os.path.exists(filefolder)
    if not isExist:
        os.makedirs(filefolder)
        print("AkShareFile:%s create" % (filefolder))
    else:
        print("AkShareFile:%s exist" % (filefolder))

    resultpath,insheetname = get_akshare_jsl(getakpath,cookie)
    print("data of path:" + resultpath + "sheetname:" +insheetname)


    va, vb = calc_value_center()
    cov_inv = calc_mahalanobis_inv()
    print("the average of unlisted bond 转股溢价率,纯债溢价率",va,vb)


    #bond_cov_jsl_df = pd.read_excel(resultpath, insheetname,converters={'pre_bond_id':str})[['bond_nm', 'stock_cd','curr_iss_amt','rating_cd','guarantor','price','year_left','ytm_rt','convert_value','premium_rt','force_redeem','convert_cd_tip','adj_cnt','adj_scnt','pre_bond_id']]
    #bond_cov_jsl_df.rename(columns={'bond_nm': '转债名称', 'stock_cd': '正股代码','curr_iss_amt':'剩余规模','rating_cd':'债券评级','guarantor':'担保情况','price':'最新价','year_left':'剩余期限','ytm_rt':'到期年化','convert_value':'转股价值','premium_rt':'转股溢价率','force_redeem':'强赎公告','convert_cd_tip':'转股提示','adj_cnt':'下修次数','adj_scnt':'成功次数','pre_bond_id':'转债代码'}, inplace=True)
    bond_cov_jsl_df = pd.read_excel(resultpath, insheetname,converters={'代码':str})[['转债名称', '正股名称','剩余规模','债券评级','现价','剩余年限','到期税前收益','转股价值','转股溢价率','代码']]


    bond_cov_jsl_df['纯债价值'] = bond_cov_jsl_df.apply(lambda row: calc_bond_value(row['现价'],row['到期税前收益'],row['剩余年限']), axis=1)
    bond_cov_jsl_df['纯债溢价率'] = bond_cov_jsl_df.apply(lambda row: calc_bond_overflow(row['现价'],row['纯债价值']), axis=1)
    bond_cov_jsl_df['转股溢价率'] = bond_cov_jsl_df.apply(lambda row: calc_stock_overflow(row['转股溢价率']), axis=1)
    bond_cov_jsl_df['含息价'] = bond_cov_jsl_df.apply(lambda row: calc_interest_value(row['现价'],row['到期税前收益'],row['剩余年限']), axis=1)

    bond_cov_jsl_df['估值距离'] = bond_cov_jsl_df.apply(lambda row: calc_value_distance(row['转股溢价率'], row['纯债溢价率'], va, vb, cov_inv), axis=1)
    

    #bond_expect_sort_df = bond_cov_jsl_df.sort_values('估值距离',ascending=True)
    bond_expect_sort_df = bond_cov_jsl_df.sort_values('剩余规模', ascending=True)
    bond_expect_sort_df = bond_expect_sort_df[['代码','转债名称','正股名称','到期税前收益','转股价值','转股溢价率','纯债价值','纯债溢价率','估值距离','现价','含息价','剩余规模','债券评级','剩余年限']]


    fileout = tnow.strftime('%Y_%m_%d') + '_out.xlsx'
    outanalypath =  "%s/%s" % (filefolder,fileout)
    writer = pd.ExcelWriter(outanalypath)
    bond_expect_sort_df.to_excel(writer, sheet_name='analyze')
    
    _, _, filters = load_jisilu_config()
    bond_kgood_df = select_kgood_some(writer, bond_expect_sort_df, 'kgood', filters)
    bond_kgood_df.to_excel(writer, sheet_name='selected')

    #writer.save()
    writer.close()
    print("value distance of  'unlist and analye' :" + fileout)

    # ── 散点图：原始坐标 + 颜色表示马氏距离 + 马氏椭圆 ──
    plot_df = bond_expect_sort_df.loc[bond_kgood_df.index].copy()

    if len(plot_df) > 0:
        # 算每只转债的马氏距离
        distances = plot_df.apply(
            lambda r: calc_value_distance(r['转股溢价率'], r['纯债溢价率'], va, vb, cov_inv), axis=1)

        # 原始协方差矩阵（用于画椭圆）
        sp = np.array([0.81, 0, -0.1, -5.56, -3, 8.34, 0.28, -5.2, -8.24, 2.34, -7.3, -26.52, -0.29])
        dp = np.array([-2.79, 0.79, 2.09, 2.58, 2.89, 4.63, 5.18, 7.33, 7.4, 7.44, 7.46, 9.23, 9.52])
        cov_mat = np.cov(np.vstack([sp, dp]), rowvar=True)
        eigen_vals, eigen_vecs = np.linalg.eigh(cov_mat)

        plt.figure(figsize=(10, 6))
        # 散点，用马氏距离着色
        sc = plt.scatter(plot_df['纯债溢价率'].values, plot_df['转股溢价率'].values,
                         c=distances.values, cmap='RdYlBu_r', s=40, edgecolors='k', linewidth=0.3)
        # 数字标记 + 图例
        n = len(plot_df)
        for i in range(n):
            plt.annotate(str(i+1), xy=(plot_df['纯债溢价率'].values[i], plot_df['转股溢价率'].values[i]),
                         xytext=(3, 3), textcoords='offset points', fontsize=5, color='black',
                         clip_on=True)

        # 理想中心
        plt.scatter(vb, va, c='red', marker='x', s=80, label='理想中心')
        # 马氏椭圆
        from matplotlib.patches import Ellipse
        # eigen_vals[0] <= eigen_vals[1], 第1列 = 大特征值方向(主轴)
        # eigenvectors 坐标 = [转股溢价率(Y), 纯债溢价率(X)]
        major_x = eigen_vecs[1, 1]  # 纯债溢价率分量
        major_y = eigen_vecs[0, 1]  # 转股溢价率分量
        angle = np.degrees(np.arctan2(major_y, major_x))
        major_len = 2 * np.sqrt(eigen_vals[1])
        minor_len = 2 * np.sqrt(eigen_vals[0])
        for d in [10, 20, 30]:
            ell = Ellipse(xy=(vb, va), width=d * major_len, height=d * minor_len,
                          angle=angle, fill=False, linestyle='--',
                          linewidth=0.8, color='gray', alpha=0.5)
            plt.gca().add_artist(ell)
            plt.text(vb + d * np.sqrt(eigen_vals[1]), va,
                     'd=%.0f' % d, fontsize=7, color='gray')

        plt.colorbar(sc, label='马氏距离')
        plt.xlabel('纯债溢价率')
        plt.ylabel('转股溢价率')
        plt.legend(fontsize=8)
        # 图例表格（分多列，每列最多 30 条）
        max_per_col = 30
        ncols = math.ceil(n / max_per_col)
        fig = plt.gcf()
        ax_table = fig.add_axes([0.76, 0.05, 0.22, 0.9], visible=False)
        ax_table.set_xlim(0, 1)
        ax_table.set_ylim(0, 1)
        for col in range(ncols):
            start = col * max_per_col
            end = min((col+1) * max_per_col, n)
            cell_text = [[str(i+1), plot_df['转债名称'].values[i]] for i in range(start, end)]
            col_widths = [0.08, 0.44]
            table_x = 0.02 + col * 0.48
            tbl = ax_table.table(cellText=cell_text, colWidths=col_widths,
                                 loc='upper left',
                                 bbox=[table_x, 0, 0.46, 0.98])
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(5)
            for key, cell in tbl.get_celld().items():
                cell.set_linewidth(0)
                cell.set_facecolor('none')
    else:
        plt.figure(figsize=(6, 4))
        plt.text(0.5, 0.5, '无满足条件的转债', ha='center', va='center',
                 transform=plt.gca().transAxes)
        plt.xlabel('纯债溢价率')
        plt.ylabel('转股溢价率')

    matplotlib.font_manager.fontManager.addfont(os.path.expanduser('~/.fonts/NotoSansCJKSC-Regular.ttf'))
    matplotlib.font_manager.fontManager.addfont(os.path.expanduser('~/.fonts/NotoSansCJKSC-Bold.ttf'))
    plt.rcParams['font.sans-serif']=['Noto Sans CJK SC', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False

    fileimage = tnow.strftime('%Y_%m_%d') + '_image.png'
    imagepath =  "%s/%s" % (filefolder,fileimage)
    plt.savefig(imagepath, dpi=150)
    plt.close()
    print("value image of  path:" + imagepath )




#对pandas中的Series和Dataframe进行排序，主要使用sort_values()和sort_index()。
#DataFrame.sort_values(by, axis=0, ascending=True, inplace=False, kind=‘quicksort’, na_position=‘last’)
#by：列名，按照某列排序
#axis：按照index排序还是按照column排序
#ascending：是否升序排列
#kind：选择 排序算法{‘quicksort’, ‘mergesort’, ‘heapsort’}, 默认是‘quicksort’，也就是快排
#na_position：nan排列的位置，是前还是后{‘first’, ‘last’}, 默认是‘last’
#sort_index() 的参数和上面差不多。





