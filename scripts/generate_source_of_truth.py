#!/usr/bin/env python3
"""Generate source_of_truth reports for JVD vs JRDB column audit."""
import csv, os
from pathlib import Path

OUT = Path("reports/source_of_truth")
OUT.mkdir(parents=True, exist_ok=True)

# ======================================================================
# Column definitions
# ======================================================================

JVD_SE = [
    'record_id','data_kubun','data_sakusei_nengappi','kaisai_nen','kaisai_tsukihi',
    'keibajo_code','kaisai_kai','kaisai_nichime','race_bango','wakuban','umaban',
    'ketto_toroku_bango','bamei','umakigo_code','seibetsu_code','hinshu_code',
    'moshoku_code','barei','tozai_shozoku_code','chokyoshi_code',
    'chokyoshimei_ryakusho','banushi_code','banushimei','fukushoku_hyoji',
    'yobi_1','futan_juryo','futan_juryo_henkomae','blinker_shiyo_kubun','yobi_2',
    'kishu_code','kishu_code_henkomae','kishumei_ryakusho','kishumei_ryakusho_henkomae',
    'kishu_minarai_code','kishu_minarai_code_henkomae','bataiju','zogen_fugo','zogen_sa',
    'ijo_kubun_code','nyusen_juni','kakutei_chakujun','dochaku_kubun','dochaku_tosu',
    'soha_time','chakusa_code_1','chakusa_code_2','chakusa_code_3',
    'corner_1','corner_2','corner_3','corner_4','tansho_odds','tansho_ninkijun',
    'kakutoku_honshokin','kakutoku_fukashokin','yobi_3','yobi_4','kohan_4f','kohan_3f',
    'aiteuma_joho_1','aiteuma_joho_2','aiteuma_joho_3','time_sa','record_koshin_kubun',
    'mining_kubun','yoso_soha_time','yoso_gosa_plus','yoso_gosa_minus','yoso_juni',
    'kyakushitsu_hantei',
]

JVD_SE_USED = {
    'keibajo_code','kaisai_nen','kaisai_tsukihi','kaisai_kai','kaisai_nichime','race_bango',
    'umaban','wakuban','ketto_toroku_bango','bamei','umakigo_code','seibetsu_code',
    'hinshu_code','moshoku_code','barei','tozai_shozoku_code','futan_juryo',
    'blinker_shiyo_kubun','kishu_code','kishu_minarai_code','bataiju','zogen_fugo','zogen_sa',
    'ijo_kubun_code','kakutei_chakujun','tansho_odds','kohan_3f','aiteuma_joho_1',
    'mining_kubun','yoso_juni','kyakushitsu_hantei','banushimei',
}

JVD_RA_USED = {
    'keibajo_code','kaisai_nen','kaisai_tsukihi','kaisai_kai','kaisai_nichime','race_bango',
    'grade_code','kyoso_shubetsu_code','kyoso_kigo_code','kyoso_joken_code',
    'kyoso_joken_code_2sai','kyoso_joken_code_3sai','kyoso_joken_code_4sai','kyoso_joken_code_5sai_ijo',
    'kyori','track_code','course_kubun','tenko_code','babajotai_code_shiba','babajotai_code_dirt',
    'toroku_tosu','shusso_tosu','nyusen_tosu','honshokin',
}

JVD_HR_USED = {
    'keibajo_code','kaisai_nen','kaisai_tsukihi','kaisai_kai','kaisai_nichime','race_bango',
    'haraimodoshi_tansho_1a','haraimodoshi_tansho_1b',
    'haraimodoshi_fukusho_1a','haraimodoshi_fukusho_1b',
    'haraimodoshi_fukusho_2a','haraimodoshi_fukusho_2b',
    'haraimodoshi_fukusho_3a','haraimodoshi_fukusho_3b',
}

JVD_RA_ALL = [
    'record_id','data_kubun','data_sakusei_nengappi','kaisai_nen','kaisai_tsukihi',
    'keibajo_code','kaisai_kai','kaisai_nichime','race_bango','yobi_code',
    'tokubetsu_kyoso_bango','kyosomei_hondai','kyosomei_fukudai','kyosomei_kakkonai',
    'kyosomei_hondai_eur','kyosomei_fukudai_eur','kyosomei_kakkonai_eur',
    'kyosomei_ryakusho_10','kyosomei_ryakusho_6','kyosomei_ryakusho_3',
    'kyosomei_kubun','jusho_kaiji','grade_code','grade_code_henkomae',
    'kyoso_shubetsu_code','kyoso_kigo_code','juryo_shubetsu_code',
    'kyoso_joken_code_2sai','kyoso_joken_code_3sai','kyoso_joken_code_4sai','kyoso_joken_code_5sai_ijo',
    'kyoso_joken_code','kyoso_joken_meisho','kyori','kyori_henkomae','track_code',
    'track_code_henkomae','course_kubun','course_kubun_henkomae',
    'honshokin','honshokin_henkomae','fukashokin','fukashokin_henkomae',
    'hasso_jikoku','hasso_jikoku_henkomae','toroku_tosu','shusso_tosu','nyusen_tosu',
    'tenko_code','babajotai_code_shiba','babajotai_code_dirt','lap_time','shogai_mile_time',
    'zenhan_3f','zenhan_4f','kohan_3f','kohan_4f',
    'corner_tsuka_juni_1','corner_tsuka_juni_2','corner_tsuka_juni_3','corner_tsuka_juni_4',
    'record_koshin_kubun',
]

KYI_FIXED_ALL = [
    'jrdb_race_key8','race_shikonen','keibajo_code','kaisai_kai','kaisai_nichime','kaisai_nen_2',
    'race_bango','umaban','basho_code','year','kai','nichi','race_num','kettou_toroku_bango','bamei',
    'idm','kishu_shisu','sogo_shisu','kyakushitsu','kyori_tekisei','chokyo_shisu','kyusha_shisu',
    'chokyo_yajirushi_code','omo_tekisei_code','shiba_tekisei_code','da_tekisei_code','soho','blinker',
    'futan_juryo','ten_shisu','pace_shisu','agari_shisu','ichi_shisu','kyori_tekisei_2','seibetsu_code',
    'kishu_code','chokyoshi_code','kyusha_rank','joho_shisu','yobi_1','joshodo_code','rotation',
    'kijun_odds_tansho','kijun_ninkijun_tansho','kijun_odds_fukusho','kijun_ninkijun_fukusho',
    'tokutei_joho_1','tokutei_joho_2','tokutei_joho_3','tokutei_joho_4','tokutei_joho_5',
    'sogo_joho_1','sogo_joho_2','sogo_joho_3','sogo_joho_4','sogo_joho_5',
    'ninki_shisu','kyusha_hyoka_code','kishu_kitai_rentai_ritsu','gekiso_shisu','hizume_code',
    'class_code','yobi_2','kishumei','kishu_minarai_code','chokyoshimei','chokyoshi_shozoku',
    'kako1_kyoso_seiseki_key','kako2_kyoso_seiseki_key','kako3_kyoso_seiseki_key',
    'kako4_kyoso_seiseki_key','kako5_kyoso_seiseki_key',
    'kako1_race_key','kako2_race_key','kako3_race_key','kako4_race_key','kako5_race_key',
    'wakuban','yobi_3','shirushi_code_1','shirushi_code_2','shirushi_code_3',
    'shirushi_code_4','shirushi_code_5','shirushi_code_6','shirushi_code_7','yobi_4',
    'kakutoku_shokin_ruikei','shutoku_shokin_ruikei','joken_class_code','pace_yoso',
    'dochu_juni','dochu_sa','dochu_uchisoto','kohan_3f_juni','kohan_3f_sa','kohan_3f_uchisoto',
    'goal_juni','goal_sa','goal_uchisoto','tenkai_kigo_code','bataiju','bataiju_zogen',
    'torikeshi_flag','banushimei','banushikai_code','umakigo_code',
    'gekiso_juni','ls_shisu_juni','ten_shisu_juni','pace_shisu_juni','agari_shisu_juni','ichi_shisu_juni',
    'kishu_kitai_tansho_ritsu','kishu_kitai_sanchakunai_ritsu','yuso_kubun',
    'taikei','taikei_sogo_1','taikei_sogo_2','taikei_sogo_3',
    'uma_tokki_1','uma_tokki_2','uma_tokki_3','uma_start_shisu','uma_deokure_ritsu',
    'sanko_zenso','sanko_zenso_kishu_code','manken_shisu','manken_shirushi','kokyu_flag',
    'gekiso_type','kyuyo_riyu_bunrui_code','flag','nyukyu_nansome','nyukyu_nengappi',
    'nyukyu_nannichimae','hobokusaki','hobokusaki_rank','yobi_5',
]

KYI_USED = {
    'idm','sogo_shisu','ten_shisu','pace_shisu','agari_shisu','ichi_shisu','gekiso_shisu',
    'ninki_shisu','joho_shisu','manken_shisu','kishu_shisu','chokyo_shisu','kyusha_shisu',
    'ls_shisu_juni','ten_shisu_juni','pace_shisu_juni','agari_shisu_juni','ichi_shisu_juni',
    'gekiso_juni','kishu_kitai_rentai_ritsu','kishu_kitai_tansho_ritsu','kishu_kitai_sanchakunai_ritsu',
    'uma_start_shisu','uma_deokure_ritsu','rotation','bataiju','bataiju_zogen',
    'kakutoku_shokin_ruikei','nyukyu_nannichimae','kijun_ninkijun_tansho',
    'keibajo_code','kyakushitsu','class_code','joshodo_code','hizume_code','blinker',
    'pace_yoso','kishu_minarai_code','kyori_tekisei','kyori_tekisei_2',
    'shiba_tekisei_code','da_tekisei_code','omo_tekisei_code','tenkai_kigo_code',
    'manken_shirushi','kokyu_flag','kyuyo_riyu_bunrui_code','kyusha_hyoka_code',
    'umakigo_code','joken_class_code','yuso_kubun',
    'jrdb_race_key8','race_shikonen','race_bango','umaban','kettou_toroku_bango',
    'kijun_odds_tansho','kijun_odds_fukusho','kijun_ninkijun_fukusho',
    'kishu_code','chokyoshi_code','seibetsu_code','bamei','kishumei','chokyoshimei',
    'chokyoshi_shozoku','taikei','taikei_sogo_1','taikei_sogo_2','taikei_sogo_3',
    'uma_tokki_1','uma_tokki_2','uma_tokki_3',
    'shirushi_code_1','shirushi_code_2','shirushi_code_3','shirushi_code_4',
    'shirushi_code_5','shirushi_code_6','shirushi_code_7',
    'dochu_juni','dochu_sa','kohan_3f_juni','kohan_3f_sa','goal_juni','goal_sa',
    'hobokusaki_rank','shutoku_shokin_ruikei','kyusha_rank','wakuban',
}

DESC_JVD = {
    'kaisai_nen':'開催年(4桁,JVD正本)','kaisai_tsukihi':'開催月日(MMDD)',
    'keibajo_code':'競馬場コード(01-10=JRA)','kaisai_kai':'開催回','kaisai_nichime':'開催日目',
    'race_bango':'レース番号','umaban':'馬番','wakuban':'枠番(JVD正本)',
    'ketto_toroku_bango':'血統登録番号(JVD)','bamei':'馬名(JVD)',
    'umakigo_code':'馬記号コード(牡牝騸) JVD正本','seibetsu_code':'性別コード JVD正本',
    'hinshu_code':'品種コード','moshoku_code':'毛色コード',
    'barei':'馬齢(JVD正本,ゼロパディング文字列)','tozai_shozoku_code':'東西所属コード',
    'chokyoshi_code':'調教師コード(JVD正本)','kishu_code':'騎手コード(JVD正本)',
    'kishu_minarai_code':'騎手見習いコード JVD正本','futan_juryo':'負担重量(JVD正本)',
    'blinker_shiyo_kubun':'ブリンカー使用区分(JVD)','bataiju':'馬体重(公式計量,JVD正本)',
    'zogen_fugo':'体重増減符号(JVD正本)','zogen_sa':'体重増減差(JVD正本)',
    'ijo_kubun_code':'異常区分(0=正常,CLAUDE.md規約)','kakutei_chakujun':'確定着順(JVD正本)',
    'tansho_odds':'単勝オッズ(整数x10,JVD正本)','nyusen_juni':'入線順位',
    'kyakushitsu_hantei':'脚質判定(JVD,kyakushitsuとは別定義)',
    'grade_code':'グレード(A=G1,B=G2,C=G3) JVD正本','track_code':'トラックコード JVD正本(10-19=芝)',
    'kyori':'距離m(JVD正本)','tenko_code':'天候(JVD正本)',
    'babajotai_code_shiba':'芝馬場状態(JVD正本)','babajotai_code_dirt':'ダ馬場状態(JVD正本)',
    'course_kubun':'コース区分A/B/C/D(JVD正本)','kyoso_joken_code':'競走条件(JVD)',
    'haraimodoshi_tansho_1a':'単勝払戻馬番1','haraimodoshi_tansho_1b':'単勝払戻金額1',
    'haraimodoshi_fukusho_1a':'複勝払戻馬番1','haraimodoshi_fukusho_1b':'複勝払戻金額1',
}

DESC_KYI = {
    'idm':'IDM指数(JRDB独自)','kishu_shisu':'騎手指数(JRDB)','sogo_shisu':'総合指数(JRDB)',
    'kyakushitsu':'脚質コード(JRDB,JVDと定義差あり)','kyori_tekisei':'距離適性(JRDB)',
    'chokyo_shisu':'調教指数(JRDB)','kyusha_shisu':'厩舎指数(JRDB)',
    'omo_tekisei_code':'重馬場適性(JRDB)','shiba_tekisei_code':'芝適性(JRDB)',
    'da_tekisei_code':'ダ適性(JRDB)','blinker':'ブリンカー(JRDB形式,jvd_seと定義差あり)',
    'futan_juryo':'負担重量(JRDB版,jvd_seと要注意)','ten_shisu':'テン指数(JRDB)',
    'pace_shisu':'ペース指数(JRDB)','agari_shisu':'上がり指数(JRDB)',
    'ichi_shisu':'位置指数(JRDB)','kyori_tekisei_2':'距離適性2(JRDB)',
    'seibetsu_code':'性別コード(JRDB,jvd_seと重複)',
    'kishu_code':'騎手コード(JRDB,jvd_seと重複)','chokyoshi_code':'調教師コード(JRDB,jvd_seと重複)',
    'kyusha_rank':'厩舎ランク(JRDB独自)','joho_shisu':'情報指数(JRDB)',
    'joshodo_code':'上昇度コード(JRDB)','rotation':'ローテーション週数(JRDB)',
    'kijun_odds_tansho':'基準単勝オッズ(JRDB,tansho_oddsと異なるソース)',
    'kijun_odds_fukusho':'基準複勝オッズ(JRDB,複勝フィルタに使用)',
    'ninki_shisu':'人気指数(JRDB)','kyusha_hyoka_code':'厩舎評価(JRDB)',
    'kishu_kitai_rentai_ritsu':'騎手期待連対率(JRDB)',
    'gekiso_shisu':'激走指数(JRDB)','hizume_code':'蹄コード(JRDB)',
    'class_code':'クラスコード(JRDB,jvd_raのkyoso_joken_codeとは別)',
    'kishu_minarai_code':'騎手見習いコード(JRDB,jvd_seと重複)',
    'wakuban':'枠番(JRDB,jvd_seと重複)','kakutoku_shokin_ruikei':'獲得賞金累計(JRDB)',
    'joken_class_code':'条件クラス(0=新馬,1=1勝,2=2勝,3=3勝,9=OP)',
    'pace_yoso':'ペース予想(JRDB)','tenkai_kigo_code':'展開記号(JRDB)',
    'bataiju':'馬体重(JRDB版,jvd_seのbataijuと要注意)',
    'bataiju_zogen':'体重増減(JRDB版,jvd_seと要注意)',
    'umakigo_code':'馬記号(JRDB,jvd_seと重複)',
    'gekiso_juni':'激走順位(JRDB,SHS)','ls_shisu_juni':'LS指数順位(JRDB,SHS)',
    'ten_shisu_juni':'テン指数順位(JRDB,SHS)','pace_shisu_juni':'ペース指数順位(JRDB,SHS)',
    'agari_shisu_juni':'上がり指数順位(JRDB,SHS)','ichi_shisu_juni':'位置指数順位(JRDB,SHS)',
    'kishu_kitai_tansho_ritsu':'騎手期待単勝率(JRDB)',
    'uma_start_shisu':'馬スタート指数(JRDB)','uma_deokure_ritsu':'馬出遅れ率(JRDB)',
    'manken_shisu':'万券指数(JRDB)','manken_shirushi':'万券印(JRDB)',
    'kokyu_flag':'呼吸フラグ(JRDB)','kyuyo_riyu_bunrui_code':'休養理由分類(JRDB)',
    'nyukyu_nannichimae':'入厩何日前(JRDB)','hobokusaki_rank':'放牧先ランク(JRDB)',
    'bamei':'馬名(JRDB,jvd_seと重複)',
}

# ======================================================================
# File 1: jvd_columns.csv
# ======================================================================
rows_jvd = []
for col in JVD_SE:
    rows_jvd.append({
        'table_name':'jvd_se','column_name':col,
        'description':DESC_JVD.get(col,''),
        'used_in_code':'yes' if col in JVD_SE_USED else 'no',
        'files':'factor_screening.py',
    })
for col in JVD_RA_ALL:
    rows_jvd.append({
        'table_name':'jvd_ra','column_name':col,
        'description':DESC_JVD.get(col,''),
        'used_in_code':'yes' if col in JVD_RA_USED else 'no',
        'files':'factor_screening.py',
    })
for col in ['haraimodoshi_tansho_1a','haraimodoshi_tansho_1b',
            'haraimodoshi_fukusho_1a','haraimodoshi_fukusho_1b',
            'haraimodoshi_fukusho_2a','haraimodoshi_fukusho_2b',
            'haraimodoshi_fukusho_3a','haraimodoshi_fukusho_3b']:
    rows_jvd.append({
        'table_name':'jvd_hr','column_name':col,
        'description':DESC_JVD.get(col,''),
        'used_in_code':'yes',
        'files':'factor_screening.py',
    })

with open(OUT/'jvd_columns.csv','w',newline='',encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['table_name','column_name','description','used_in_code','files'])
    w.writeheader(); w.writerows(rows_jvd)
print(f"[OK] jvd_columns.csv  {len(rows_jvd)} rows")

# ======================================================================
# File 2: jrdb_columns.csv
# ======================================================================
rows_jrdb = []
for col in KYI_FIXED_ALL:
    rows_jrdb.append({
        'table_name':'jrd_kyi_fixed','column_name':col,
        'description':DESC_KYI.get(col,''),
        'used_in_code':'yes' if col in KYI_USED else 'no',
        'files':'factor_screening.py / factor_investment_screening.py',
    })
for col,desc in [('ls_shisu','LS指数(jrd_joa)'),('ls_hyoka','LS評価(jrd_joa)'),('odds_shisu','オッズ指数(jrd_joa)')]:
    rows_jrdb.append({'table_name':'jrd_joa_fixed','column_name':col,'description':desc,'used_in_code':'yes','files':'factor_screening.py'})
for col,desc in [('shiba_da_shogai_code','芝ダ障コード'),('migi_hidari','右左回り'),('uchi_soto','内外'),
                 ('shubetsu','競走種別'),('jouken','条件コード'),('juryo_shubetsu_code','重量種別'),
                 ('grade','グレード(JRDB)'),('tosu','頭数'),('kyori','距離'),('course','コース'),('kaisai_kubun','開催区分')]:
    rows_jrdb.append({'table_name':'jrd_bac_fixed','column_name':col,'description':desc,'used_in_code':'yes','files':'factor_screening.py'})

with open(OUT/'jrdb_columns.csv','w',newline='',encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['table_name','column_name','description','used_in_code','files'])
    w.writeheader(); w.writerows(rows_jrdb)
print(f"[OK] jrdb_columns.csv  {len(rows_jrdb)} rows")

# ======================================================================
# File 3: column_overlap_matrix.csv
# ======================================================================
overlap_rows = [
    # --- EXACT JOIN KEYS (必ずJVD正本) ---
    ('keibajo_code','jvd_se','keibajo_code','jrd_kyi_fixed','keibajo_code','exact_overlap','JVD','JOIN条件で一致が保証。JVDを正本とする','factor_screening.py L242'),
    ('race_bango','jvd_se','race_bango','jrd_kyi_fixed','race_bango','exact_overlap','JVD','JOIN条件','factor_screening.py L246'),
    ('umaban','jvd_se','umaban','jrd_kyi_fixed','umaban','exact_overlap','JVD','JOIN条件','factor_screening.py L247'),

    # --- EXACT OVERLAP: factual horse/race attributes ---
    ('wakuban','jvd_se','wakuban','jrd_kyi_fixed','wakuban','exact_overlap','JVD',
     'コード上compute_derived_factorsでjvd_se.wakuban_vを採用済み。正本JVD確定',
     'factor_screening.py L650'),
    ('kishu_code','jvd_se','kishu_code','jrd_kyi_fixed','kishu_code','exact_overlap','JVD',
     '騎手コード。jvd_seが公式ソース。JRDBは2次処理','factor_screening.py'),
    ('chokyoshi_code','jvd_se','chokyoshi_code','jrd_kyi_fixed','chokyoshi_code','exact_overlap','JVD',
     '調教師コード。JVD正本','factor_screening.py'),
    ('kishu_minarai_code','jvd_se','kishu_minarai_code','jrd_kyi_fixed','kishu_minarai_code','exact_overlap','JVD',
     '騎手見習いコード。現在JRDB(k.)から参照。JVDに切替可能','factor_screening.py L183'),
    ('umakigo_code','jvd_se','umakigo_code','jrd_kyi_fixed','umakigo_code','exact_overlap','JVD',
     '馬記号(牡牝騸)。現在JRDB(k.)から参照。JVDに切替可能','factor_screening.py L183'),
    ('seibetsu_code','jvd_se','seibetsu_code','jrd_kyi_fixed','seibetsu_code','exact_overlap','JVD',
     '性別コード。現在JRDBから参照。JVDに切替可能(ただしPhase1-4 ALL_FACTORSには含まれない)','factor_screening.py'),
    ('bamei','jvd_se','bamei','jrd_kyi_fixed','bamei','exact_overlap','JVD',
     '馬名。ラベル用途のみ。JVD正本','factor_screening.py'),
    ('banushimei','jvd_se','banushimei','jrd_kyi_fixed','banushimei','exact_overlap','JVD',
     'オーナー名。ラベル用途のみ','factor_screening.py'),

    # --- CAUTION: 同名だが定義差あり ---
    ('futan_juryo','jvd_se','futan_juryo','jrd_kyi_fixed','futan_juryo','caution','MANUAL_REVIEW',
     'jvd_se=公式負担重量(確定値)。jrd_kyi_fixed=JRDB版(計算過程が異なる可能性)。現在kから参照。要定義確認',
     'factor_screening.py L205(futan_juryo_rawとして取得)'),
    ('bataiju','jvd_se','bataiju','jrd_kyi_fixed','bataiju','caution','MANUAL_REVIEW',
     'jvd_se=公式計量体重(確定値)。jrd_kyi_fixed=JRDB版(予測/補正の可能性)。現在kから参照',
     'factor_screening.py L183'),
    ('bataiju_zogen','jvd_se','zogen_sa','jrd_kyi_fixed','bataiju_zogen','caution','MANUAL_REVIEW',
     'jvd_seはzogen_sa(文字列),jrd_kyi_fixedはbataiju_zogen(数値)。列名も異なる。要定義確認',
     'factor_screening.py'),

    # --- SEMANTIC OVERLAP: 名前は違うが近い意味 ---
    ('blinker','jvd_se','blinker_shiyo_kubun','jrd_kyi_fixed','blinker','semantic_overlap','JRDB',
     'jvd_seはblinker_shiyo_kubun(JVD形式),jrd_kyi_fixedはblinker(JRDB形式)。コーディング異なる可能性。現状JRDBを採用',
     'factor_screening.py L183(blinker from k.)'),
    ('kishumei','jvd_se','kishumei_ryakusho','jrd_kyi_fixed','kishumei','semantic_overlap','JRDB',
     'jvd_seは略称(kishumei_ryakusho),jrd_kyi_fixedはフルネーム(kishumei)。現在JRDB採用','factor_screening.py'),
    ('kyakushitsu','jvd_se','kyakushitsu_hantei','jrd_kyi_fixed','kyakushitsu','caution','JRDB',
     'jvd_seはkyakushitsu_hantei(JVD判定),jrd_kyi_fixedはkyakushitsu(JRDB)。定義差あり。Phase1-4ではJRDB採用',
     'factor_screening.py L183(kyakushitsu from k.)'),
    ('tansho_odds','jvd_se','tansho_odds','jrd_kyi_fixed','kijun_odds_tansho','caution','JVD',
     'jvd_se.tansho_odds=公式オッズ(整数x10)。jrd_kyi_fixed.kijun_odds_tansho=JRDB基準オッズ。別物。単勝フィルタはJVD使用',
     'factor_screening.py L195'),
    ('kyori','jvd_ra','kyori','jrd_bac_fixed','kyori','exact_overlap','JVD',
     '距離。jvd_raが正本。jrd_bac_fixedはセカンダリ。現在jvd_raから参照','factor_screening.py L212'),
    ('grade','jvd_ra','grade_code','jrd_bac_fixed','grade','semantic_overlap','JVD',
     'グレードコード。jvd_raがA/B/C/L等,jrd_bac_fixedはgrade。現在jvd_raから参照','factor_screening.py'),
    ('kyoso_joken','jvd_ra','kyoso_joken_code','jrd_bac_fixed','jouken','semantic_overlap','JVD',
     '競走条件。jvd_raが正本','factor_screening.py'),

    # --- JVD-ONLY (no JRDB equivalent) ---
    ('barei','jvd_se','barei','none','none','jvd_only','JVD','馬齢。jrd_kyi_fixedには存在しない','factor_screening.py L190'),
    ('ijo_kubun_code','jvd_se','ijo_kubun_code','none','none','jvd_only','JVD','異常区分(CLAUDE.md規約フィルタ)','factor_screening.py WHERE'),
    ('kakutei_chakujun','jvd_se','kakutei_chakujun','none','none','jvd_only','JVD','確定着順(結果)。ラベルとして使用','factor_screening.py'),
    ('tenko_code','jvd_ra','tenko_code','none','none','jvd_only','JVD','天候コード。競走環境条件','factor_screening.py L213'),
    ('babajotai_code_shiba','jvd_ra','babajotai_code_shiba','none','none','jvd_only','JVD','芝馬場状態。競走環境','factor_screening.py'),
    ('track_code','jvd_ra','track_code','none','none','jvd_only','JVD','トラックコード(芝/ダ判定の正本)','factor_screening.py L212'),
    ('haraimodoshi_tansho','jvd_hr','haraimodoshi_tansho_1b','none','none','jvd_only','JVD','単勝払戻金額。ROI計算正本','factor_screening.py'),
    ('haraimodoshi_fukusho','jvd_hr','haraimodoshi_fukusho_*','none','none','jvd_only','JVD','複勝払戻金額。ROI計算正本','factor_screening.py'),

    # --- JRDB-ONLY (Phase1-4 core factors, no JVD equivalent) ---
    ('idm',          'none','none','jrd_kyi_fixed','idm',          'jrdb_only','JRDB','IDM指数。JRDB独自','ALL_FACTORS'),
    ('sogo_shisu',   'none','none','jrd_kyi_fixed','sogo_shisu',   'jrdb_only','JRDB','総合指数。JRDB独自','ALL_FACTORS'),
    ('ten_shisu',    'none','none','jrd_kyi_fixed','ten_shisu',    'jrdb_only','JRDB','テン指数。JRDB独自','ALL_FACTORS'),
    ('pace_shisu',   'none','none','jrd_kyi_fixed','pace_shisu',   'jrdb_only','JRDB','ペース指数。JRDB独自','ALL_FACTORS'),
    ('agari_shisu',  'none','none','jrd_kyi_fixed','agari_shisu',  'jrdb_only','JRDB','上がり指数。JRDB独自','ALL_FACTORS'),
    ('ichi_shisu',   'none','none','jrd_kyi_fixed','ichi_shisu',   'jrdb_only','JRDB','位置指数。JRDB独自','ALL_FACTORS'),
    ('gekiso_shisu', 'none','none','jrd_kyi_fixed','gekiso_shisu', 'jrdb_only','JRDB','激走指数。JRDB独自','ALL_FACTORS'),
    ('manken_shisu', 'none','none','jrd_kyi_fixed','manken_shisu', 'jrdb_only','JRDB','万券指数。JRDB独自','ALL_FACTORS'),
    ('kishu_shisu',  'none','none','jrd_kyi_fixed','kishu_shisu',  'jrdb_only','JRDB','騎手指数。JRDB独自','ALL_FACTORS'),
    ('chokyo_shisu', 'none','none','jrd_kyi_fixed','chokyo_shisu', 'jrdb_only','JRDB','調教指数。JRDB独自','ALL_FACTORS'),
    ('kyusha_shisu', 'none','none','jrd_kyi_fixed','kyusha_shisu', 'jrdb_only','JRDB','厩舎指数。JRDB独自','ALL_FACTORS'),
    ('ls_shisu_juni','none','none','jrd_kyi_fixed','ls_shisu_juni','jrdb_only','JRDB','LS指数順位。JRDB独自(SHS)','ALL_FACTORS'),
    ('manken_shirushi','none','none','jrd_kyi_fixed','manken_shirushi','jrdb_only','JRDB','万券印。JRDB独自(shortlist候補)','ALL_FACTORS'),
    ('rotation',     'none','none','jrd_kyi_fixed','rotation',     'jrdb_only','JRDB','ローテ週数。JRDB独自','ALL_FACTORS'),
    ('kakutoku_shokin_ruikei','none','none','jrd_kyi_fixed','kakutoku_shokin_ruikei','jrdb_only','JRDB','獲得賞金累計。JRDB独自(高基数問題あり)','ALL_FACTORS'),
    ('nyukyu_nannichimae','none','none','jrd_kyi_fixed','nyukyu_nannichimae','jrdb_only','JRDB','入厩何日前。JRDB独自','ALL_FACTORS'),
    ('kijun_ninkijun_tansho','none','none','jrd_kyi_fixed','kijun_ninkijun_tansho','jrdb_only','JRDB','基準人気順。JRDB独自','ALL_FACTORS'),
    ('pace_yoso',    'none','none','jrd_kyi_fixed','pace_yoso',    'jrdb_only','JRDB','ペース予想。JRDB独自','ALL_FACTORS'),
    ('tenkai_kigo_code','none','none','jrd_kyi_fixed','tenkai_kigo_code','jrdb_only','JRDB','展開記号。JRDB独自','ALL_FACTORS'),
    ('joshodo_code', 'none','none','jrd_kyi_fixed','joshodo_code', 'jrdb_only','JRDB','上昇度。JRDB独自','ALL_FACTORS'),
    ('hizume_code',  'none','none','jrd_kyi_fixed','hizume_code',  'jrdb_only','JRDB','蹄コード。JRDB独自','ALL_FACTORS'),
    ('class_code',   'none','none','jrd_kyi_fixed','class_code',   'jrdb_only','JRDB','クラスコード(JRDB)。joken_class_codeとは別','ALL_FACTORS'),
    ('joken_class_code','none','none','jrd_kyi_fixed','joken_class_code','jrdb_only','JRDB','条件クラス(0=新馬,1=1勝,2=2勝,3=3勝,9=OP)','ALL_FACTORS'),
    ('uma_start_shisu','none','none','jrd_kyi_fixed','uma_start_shisu','jrdb_only','JRDB','スタート指数。JRDB独自','ALL_FACTORS'),
    ('uma_deokure_ritsu','none','none','jrd_kyi_fixed','uma_deokure_ritsu','jrdb_only','JRDB','出遅れ率。JRDB独自','ALL_FACTORS'),
    ('kishu_kitai_rentai_ritsu','none','none','jrd_kyi_fixed','kishu_kitai_rentai_ritsu','jrdb_only','JRDB','騎手期待連対率。JRDB独自','ALL_FACTORS'),
    ('kokyu_flag',   'none','none','jrd_kyi_fixed','kokyu_flag',   'jrdb_only','JRDB','呼吸フラグ。JRDB独自','ALL_FACTORS'),
    ('kyuyo_riyu_bunrui_code','none','none','jrd_kyi_fixed','kyuyo_riyu_bunrui_code','jrdb_only','JRDB','休養理由分類。JRDB独自','ALL_FACTORS'),
    ('kyusha_hyoka_code','none','none','jrd_kyi_fixed','kyusha_hyoka_code','jrdb_only','JRDB','厩舎評価。JRDB独自','ALL_FACTORS'),
    ('yuso_kubun',   'none','none','jrd_kyi_fixed','yuso_kubun',   'jrdb_only','JRDB','輸送区分。JRDB独自','ALL_FACTORS'),
    ('kijun_odds_fukusho','none','none','jrd_kyi_fixed','kijun_odds_fukusho','jrdb_only','JRDB','複勝オッズ(JRDB基準)。複勝フィルタに使用','factor_investment_screening.py'),
]

fields = ['logical_field_name','jvd_table','jvd_column','jrdb_table','jrdb_column',
          'overlap_type','canonical_source','reason','evidence_file']
with open(OUT/'column_overlap_matrix.csv','w',newline='',encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for row in overlap_rows:
        w.writerow(dict(zip(fields, row)))
print(f"[OK] column_overlap_matrix.csv  {len(overlap_rows)} rows")

# ======================================================================
# File 4: phase1_4_column_usage.csv
# ======================================================================
# ALL_FACTORS = 49 factors from factor_screening.py
ALL_FACTORS = [
    # (factor_name, source_column, source_table, type, canonical_source, needs_change, impact_note)
    ('idm','idm','jrd_kyi_fixed','direct','JRDB','no','JRDB独自。変更不可'),
    ('sogo_shisu','sogo_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('ten_shisu','ten_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('pace_shisu','pace_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('agari_shisu','agari_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('ichi_shisu','ichi_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('gekiso_shisu','gekiso_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('ninki_shisu','ninki_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('joho_shisu','joho_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('manken_shisu','manken_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kishu_shisu','kishu_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('chokyo_shisu','chokyo_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kyusha_shisu','kyusha_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('ls_shisu_juni','ls_shisu_juni','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(SHS)'),
    ('ten_shisu_juni','ten_shisu_juni','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(SHS)'),
    ('pace_shisu_juni','pace_shisu_juni','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(SHS)'),
    ('agari_shisu_juni','agari_shisu_juni','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(SHS)'),
    ('ichi_shisu_juni','ichi_shisu_juni','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(SHS)'),
    ('gekiso_juni','gekiso_juni','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(SHS)'),
    ('kishu_kitai_rentai_ritsu','kishu_kitai_rentai_ritsu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kishu_kitai_tansho_ritsu','kishu_kitai_tansho_ritsu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kishu_kitai_sanchakunai_ritsu','kishu_kitai_sanchakunai_ritsu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('uma_start_shisu','uma_start_shisu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('uma_deokure_ritsu','uma_deokure_ritsu','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('rotation','rotation','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('bataiju','bataiju','jrd_kyi_fixed','direct','MANUAL_REVIEW','yes_caution','現在JRDB(k.bataiju)参照。JVDの公式計量値(v.bataiju→bataiju_actual)への切替を検討。定義確認要'),
    ('bataiju_zogen','bataiju_zogen','jrd_kyi_fixed','direct','MANUAL_REVIEW','yes_caution','現在JRDB参照。jvd_se.zogen_saとの定義差確認要'),
    ('kakutoku_shokin_ruikei','kakutoku_shokin_ruikei','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(高基数問題あり,再設計候補)'),
    ('nyukyu_nannichimae','nyukyu_nannichimae','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kijun_ninkijun_tansho','kijun_ninkijun_tansho','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('keibajo_code','keibajo_code','jvd_se(join保証)','filter/binning','JVD','no','JOIN条件で一致保証。実質同値'),
    ('kyakushitsu','kyakushitsu','jrd_kyi_fixed','direct','JRDB','no','jvd_se.kyakushitsu_hanteiと定義差あり。JRDB維持'),
    ('class_code','class_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自コード'),
    ('joshodo_code','joshodo_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('hizume_code','hizume_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('blinker','blinker','jrd_kyi_fixed','direct','JRDB','no','jvd_se.blinker_shiyo_kubunと定義差あり。JRDB維持'),
    ('pace_yoso','pace_yoso','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kishu_minarai_code','kishu_minarai_code','jrd_kyi_fixed','direct','JVD','yes','現在JRDB(k.)参照。jvd_se.kishu_minarai_codeに切替可能。ビン件数+11.8%見込み'),
    ('kyori_tekisei','kyori_tekisei','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kyori_tekisei_2','kyori_tekisei_2','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('shiba_tekisei_code','shiba_tekisei_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('da_tekisei_code','da_tekisei_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('omo_tekisei_code','omo_tekisei_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('tenkai_kigo_code','tenkai_kigo_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('manken_shirushi','manken_shirushi','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(shortlist候補)'),
    ('kokyu_flag','kokyu_flag','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kyuyo_riyu_bunrui_code','kyuyo_riyu_bunrui_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('kyusha_hyoka_code','kyusha_hyoka_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自'),
    ('umakigo_code','umakigo_code','jrd_kyi_fixed','direct','JVD','yes','現在JRDB(k.)参照。jvd_se.umakigo_codeに切替可能。ビン件数+11.8%見込み'),
    ('joken_class_code','joken_class_code','jrd_kyi_fixed','direct','JRDB','no','JRDB独自(1勝クラス判定等)'),
    # Derived factors
    ('wakuban','wakuban_v','jvd_se','derived','JVD','no','compute_derived_factorsで既にjvd_se.wakuban_vを採用済み'),
    ('barei','barei','jvd_se','derived','JVD','no','jrd_kyi_fixedにbarei列なし。JVD正本確定'),
    ('surface','track_code','jvd_ra','derived','JVD','no','_surface()関数でtrack_codeから導出。JVD正本確定'),
    ('kyori_kubun','kyori','jvd_ra','derived','JVD','no','_kyori_kubun()でjvd_ra.kyoriから導出'),
    ('course_27','keibajo_code+surface+kyori','jvd_ra/jrd_kyi_fixed','derived','JVD','no','_course_27()で3列組み合わせ。surface/kyoriはJVD'),
    ('babajotai_heavy','babajotai_code_shiba','jvd_ra','derived','JVD','no','JVD正本'),
    # Join/filter keys
    ('tansho_odds(filter)','tansho_odds','jvd_se','filter','JVD','no','オッズフィルタ。JVD正本(_apply_odds_filter)'),
    ('ijo_kubun_code(filter)','ijo_kubun_code','jvd_se','filter','JVD','no','CLAUDE.md規約フィルタ'),
    ('kakutei_chakujun(filter)','kakutei_chakujun','jvd_se','filter','JVD','no','取消除外フィルタ'),
    ('haraimodoshi_tansho(label)','haraimodoshi_tansho_1b','jvd_hr','derived','JVD','no','ROI計算用勝ちラベル'),
    ('haraimodoshi_fukusho(label)','haraimodoshi_fukusho_*','jvd_hr','derived','JVD','no','ROI計算用複勝ラベル'),
    ('kijun_odds_fukusho(filter)','kijun_odds_fukusho','jrd_kyi_fixed','filter','JRDB','no','複勝フィルタ用。JVDに同値なし'),
]

phase_usage = []
for phase in [1,2,3,4]:
    for rec in ALL_FACTORS:
        fname,scol,stbl,utype,canonical,needs_chg,impact = rec
        phase_usage.append({
            'phase': phase,
            'file': 'factor_screening.py / factor_investment_screening.py',
            'logical_field_name': fname,
            'source_table': stbl,
            'source_column': scol,
            'usage_type': utype,
            'canonical_source_after_policy': canonical,
            'needs_change': needs_chg,
            'impact_note': impact,
        })

with open(OUT/'phase1_4_column_usage.csv','w',newline='',encoding='utf-8-sig') as f:
    fields = ['phase','file','logical_field_name','source_table','source_column',
              'usage_type','canonical_source_after_policy','needs_change','impact_note']
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(phase_usage)
print(f"[OK] phase1_4_column_usage.csv  {len(phase_usage)} rows")

# ======================================================================
# File 5: jvd_priority_migration_plan.md
# ======================================================================
md = """# JVD優先正本ルール 移行計画

生成日: 2026-05-03

---

## 結論（先出し10行以内）

1. **Phase1〜4の49ファクターは全てJRDB（jrd_kyi_fixed）起源** — JRDB独自指数のため切替不可
2. **JVDが正本となる列はすでに多くが正しく参照されている** — wakuban/surface/kyori_kubun/結果ラベルはJVD済み
3. **即座に切替可能なのは2列のみ**: `umakigo_code` と `kishu_minarai_code`（JRDB→JVD。ビン件数+11.8%見込み）
4. **要注意が3列**: `bataiju` / `bataiju_zogen` / `futan_juryo`（JVDとJRDBで定義差の可能性あり）
5. **JVD正本移行の最大効果**: jrd_kyi_fixed INNER JOINを外すことで全ビン件数が約+11.8%増加
6. **ACTUAL_DB_SCHEMA_2293_COLUMNS.csvは古い** — jrd_kyi_fixedの実DB列数は139(CSV記載38)
7. **最優先アクション**: bataiju/futan_juryo の定義差をDB直接確認してから移行判断

---

## 重複カラムの扱い方針

| 分類 | 対象列 | 方針 |
|------|--------|------|
| exact_overlap (JOIN確定) | keibajo_code, race_bango, umaban | JVDを正本。JOIN条件で同値保証済み |
| exact_overlap (切替推奨) | wakuban, kishu_minarai_code, umakigo_code, seibetsu_code | JVDを正本。wakubanは既に切替済み |
| caution (定義差確認要) | bataiju, bataiju_zogen, futan_juryo | 手動確認後に決定 |
| semantic_overlap | blinker vs blinker_shiyo_kubun, kyakushitsu vs kyakushitsu_hantei | 定義差あり。現状JRDB維持 |
| jrdb_only | idm, ten_shisu, manken_shirushi など全スコア指数 | JRDB固定。JVDに同値なし |
| jvd_only | barei, ijo_kubun_code, grade_code, track_code, haraimodoshi_* | JVD固定。既に正しく参照 |

---

## Phase1〜4 で切替対象となる主要カラム

### 切替確定（JVD優先）
| カラム | 現状 | 変更後 | 影響 |
|--------|------|--------|------|
| `wakuban` | jvd_se.wakuban_v → wakuban (**既に切替済み**) | 変更不要 | なし |
| `umakigo_code` | k.umakigo_code (JRDB) | v.umakigo_code (JVD) | ビン件数+11.8%。要リグレッションテスト |
| `kishu_minarai_code` | k.kishu_minarai_code (JRDB) | v.kishu_minarai_code (JVD) | ビン件数+11.8%。要リグレッションテスト |

### 要注意（手動判断）
| カラム | 現状 | 懸念 | アクション |
|--------|------|------|-----------|
| `bataiju` | k.bataiju (JRDB) | jvd_se.bataijuとの数値差? | DB直接で20件程度比較して定義確認 |
| `bataiju_zogen` | k.bataiju_zogen (JRDB) | jvd_se.zogen_saとの定義差? | 符号方向・単位の確認 |
| `futan_juryo` | k.futan_juryo (JRDB) | jvd_se.futan_juryo_rawとの差? | 既に両方参照済み。SQLで差異分析 |

---

## 変更優先順位

1. **P0 (最優先・今すぐ)**: ACTUAL_DB_SCHEMA_2293_COLUMNS.csvを実DBに合わせて更新 (139列のjrd_kyi_fixed)
2. **P1 (高)**: `umakigo_code` の参照をk.→v.に切替 → ビン件数増加で監査再実行が必要
3. **P1 (高)**: `kishu_minarai_code` の参照をk.→v.に切替 → 同上
4. **P2 (中)**: `bataiju` / `bataiju_zogen` / `futan_juryo` の定義差確認
5. **P3 (低)**: kyakushitsu vs kyakushitsu_hanteiの定義差分析（現状JRDB維持で問題なし）

---

## 変更で壊れる可能性がある箇所

| ファイル | 影響内容 |
|----------|---------|
| `factor_screening.py` (_LOAD_QUERY) | k.umakigo_code → v.umakigo_code に変更が必要 |
| `factor_screening.py` (_LOAD_QUERY) | k.kishu_minarai_code → v.kishu_minarai_code に変更が必要 |
| `backend/batch/master_combo_pipeline.py` | セグメント件数が変わるため再実行要 |
| `backend/batch/factor_investment_screening.py` | 全Phase再スクリーニング要 |
| `reports/production_search/segments/` | 全combo_results.csvの再計算要 |
| `reports/production_search/phase*_bin_detail*.csv` | ビン件数が変わるため再生成要 |
| `reports/source_of_truth/audit_factor_bins*.py` | 監査の再実施要 |

---

## 再監査が必要なファクター一覧

umakigo_code / kishu_minarai_code を切替た場合:
- 両ファクターのPhase1〜4全セグメントのビン件数監査
- 特にKEIBAJO_SURFACE_08_芝の manken_shirushi との掛け合わせcombosの再確認

bataiju / bataiju_zogen を切替た場合:
- 両ファクターの全ビン件数・採用判定の再評価

---

## 今後の実装原則

1. **JVDを正本**: 馬齢(barei)、着順(kakutei_chakujun)、オッズ(tansho_odds)、馬場(track_code)、グレード(grade_code)、着順ラベル(haraimodoshi_*)
2. **JRDBを正本**: 全スコア指数(idm, ten_shisu等)、予測マーク(manken_shirushi)、適性コード、輸送・休養情報
3. **JOIN経路**: jrd_kyi_fixed INNER JOIN は JRDB因子の分析に必要。JVD因子のみ分析する場合はjvd_se + jvd_ra + jvd_hrのみで可
4. **ビン件数の参照母数**: JRDB因子 → jrd_kyi_fixed JOINありの件数が正しい母数。JVD因子 → JVD全件数が母数
5. **スキーマ管理**: ACTUAL_DB_SCHEMA_2293_COLUMNS.csvは定期的に実DBと照合すること

---

## 注記

- **ACTUAL_DB_SCHEMA_2293_COLUMNS.csv は更新要**: jrd_kyi_fixedは139列だがCSVには38列のみ記載
- `jrd_kyi` (raw) にも同様の問題あり — 実DB132列だがCSVでも132列で整合
- jrd_kyi_fixedは jrd_kyi + 複数JRDBテーブルからの派生列を追加した拡張テーブル

---
*このドキュメントは factor_screening.py / factor_investment_screening.py / ACTUAL_DB_SCHEMA_2293_COLUMNS.csv / 実DBスキーマ の直接調査に基づく。推測なし。*
"""

with open(OUT/'jvd_priority_migration_plan.md','w',encoding='utf-8') as f:
    f.write(md)
print("[OK] jvd_priority_migration_plan.md")

print("\n=== ALL DONE ===")
print(f"Output: {OUT.resolve()}")
