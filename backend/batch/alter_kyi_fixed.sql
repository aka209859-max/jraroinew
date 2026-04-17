-- ============================================================================
-- jrd_kyi_fixed テーブル拡張 ALTER TABLE
-- 目的: jrd_kyi の132カラムのうち、jrd_kyi_fixed に存在しない101カラムを追加
-- 既存38カラム（リネーム済み含む）はそのまま維持
-- PostgreSQL 9.6+ の IF NOT EXISTS 構文使用（冪等実行可能）
-- ============================================================================

-- (1) joho_shisu (情報指数) varchar(5)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS joho_shisu VARCHAR(5);

-- (2) yobi_1 (予備1) varchar(15)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS yobi_1 VARCHAR(15);

-- (3) joshodo_code (上昇度コード) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS joshodo_code VARCHAR(1);

-- (4) rotation (ローテーション) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS rotation VARCHAR(3);

-- (5) kijun_odds_tansho (基準オッズ単勝) varchar(5)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kijun_odds_tansho VARCHAR(5);

-- (6) kijun_ninkijun_tansho (基準人気順単勝) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kijun_ninkijun_tansho VARCHAR(2);

-- (7) kijun_odds_fukusho (基準オッズ複勝) varchar(5)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kijun_odds_fukusho VARCHAR(5);

-- (8) kijun_ninkijun_fukusho (基準人気順複勝) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kijun_ninkijun_fukusho VARCHAR(2);

-- (9)～(13) tokutei_joho_1〜5 (特定情報1〜5) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS tokutei_joho_1 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS tokutei_joho_2 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS tokutei_joho_3 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS tokutei_joho_4 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS tokutei_joho_5 VARCHAR(3);

-- (14)～(18) sogo_joho_1〜5 (総合情報1〜5) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sogo_joho_1 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sogo_joho_2 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sogo_joho_3 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sogo_joho_4 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sogo_joho_5 VARCHAR(3);

-- (19) ninki_shisu (人気指数) varchar(5)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS ninki_shisu VARCHAR(5);

-- (20) kyusha_hyoka_code (厩舎評価コード) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kyusha_hyoka_code VARCHAR(1);

-- (21) kishu_kitai_rentai_ritsu (騎手期待連対率) varchar(4)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kishu_kitai_rentai_ritsu VARCHAR(4);

-- (22) gekiso_shisu (激走指数) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS gekiso_shisu VARCHAR(3);

-- (23) hizume_code (蹄コード) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS hizume_code VARCHAR(2);

-- (24) class_code (クラスコード) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS class_code VARCHAR(2);

-- (25) yobi_2 (予備2) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS yobi_2 VARCHAR(2);

-- (26) kishumei (騎手名) varchar(12)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kishumei VARCHAR(12);

-- (27) kishu_minarai_code (騎手見習コード) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kishu_minarai_code VARCHAR(1);

-- (28) chokyoshimei (調教師名) varchar(12)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS chokyoshimei VARCHAR(12);

-- (29) chokyoshi_shozoku (調教師所属) varchar(4)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS chokyoshi_shozoku VARCHAR(4);

-- (30)～(34) kako1〜5_kyoso_seiseki_key (過去1〜5競走成績キー) varchar(16)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako1_kyoso_seiseki_key VARCHAR(16);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako2_kyoso_seiseki_key VARCHAR(16);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako3_kyoso_seiseki_key VARCHAR(16);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako4_kyoso_seiseki_key VARCHAR(16);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako5_kyoso_seiseki_key VARCHAR(16);

-- (36)～(40) kako1〜5_race_key (過去1〜5レースキー) varchar(8)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako1_race_key VARCHAR(8);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako2_race_key VARCHAR(8);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako3_race_key VARCHAR(8);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako4_race_key VARCHAR(8);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kako5_race_key VARCHAR(8);

-- (41) wakuban (枠番) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS wakuban VARCHAR(1);

-- (42) yobi_3 (予備3) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS yobi_3 VARCHAR(2);

-- (43)～(47) shirushi_code_1〜7 (印コード1〜7) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_1 VARCHAR(1);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_2 VARCHAR(1);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_3 VARCHAR(1);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_4 VARCHAR(1);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_5 VARCHAR(1);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_6 VARCHAR(1);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shirushi_code_7 VARCHAR(1);

-- (48) yobi_4 (予備4) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS yobi_4 VARCHAR(1);

-- (49) kakutoku_shokin_ruikei (獲得賞金累計) varchar(6)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kakutoku_shokin_ruikei VARCHAR(6);

-- (50) shutoku_shokin_ruikei (収得賞金累計) varchar(5)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS shutoku_shokin_ruikei VARCHAR(5);

-- 51 joken_class_code (条件クラスコード) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS joken_class_code VARCHAR(1);

-- 52 pace_yoso (ペース予想) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS pace_yoso VARCHAR(1);

-- 53 dochu_juni (道中順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS dochu_juni VARCHAR(2);

-- 54 dochu_sa (道中差) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS dochu_sa VARCHAR(2);

-- 55 dochu_uchisoto (道中内外) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS dochu_uchisoto VARCHAR(1);

-- 56 kohan_3f_juni (後半3F順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kohan_3f_juni VARCHAR(2);

-- 57 kohan_3f_sa (後半3F差) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kohan_3f_sa VARCHAR(2);

-- 58 kohan_3f_uchisoto (後半3F内外) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kohan_3f_uchisoto VARCHAR(1);

-- 59 goal_juni (ゴール順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS goal_juni VARCHAR(2);

-- 60 goal_sa (ゴール差) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS goal_sa VARCHAR(2);

-- 61 goal_uchisoto (ゴール内外) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS goal_uchisoto VARCHAR(1);

-- 62 tenkai_kigo_code (展開記号コード) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS tenkai_kigo_code VARCHAR(1);

-- 63 bataiju (馬体重) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS bataiju VARCHAR(3);

-- 64 bataiju_zogen (馬体重増減) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS bataiju_zogen VARCHAR(3);

-- 65 torikeshi_flag (取消フラグ) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS torikeshi_flag VARCHAR(1);

-- 66 banushimei (馬主名) varchar(40)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS banushimei VARCHAR(40);

-- 67 banushikai_code (馬主会コード) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS banushikai_code VARCHAR(2);

-- 68 umakigo_code (馬記号コード) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS umakigo_code VARCHAR(2);

-- 69 gekiso_juni (激走順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS gekiso_juni VARCHAR(2);

-- 70 ls_shisu_juni (LS指数順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS ls_shisu_juni VARCHAR(2);

-- 71 ten_shisu_juni (テン指数順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS ten_shisu_juni VARCHAR(2);

-- 72 pace_shisu_juni (ペース指数順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS pace_shisu_juni VARCHAR(2);

-- 73 agari_shisu_juni (上がり指数順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS agari_shisu_juni VARCHAR(2);

-- 74 ichi_shisu_juni (位置指数順位) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS ichi_shisu_juni VARCHAR(2);

-- 75 kishu_kitai_tansho_ritsu (騎手期待単勝率) varchar(4)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kishu_kitai_tansho_ritsu VARCHAR(4);

-- 76 kishu_kitai_sanchakunai_ritsu (騎手期待3着内率) varchar(4)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kishu_kitai_sanchakunai_ritsu VARCHAR(4);

-- 77 yuso_kubun (輸送区分) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS yuso_kubun VARCHAR(1);

-- 78 taikei (体型) varchar(24)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS taikei VARCHAR(24);

-- 79～81 taikei_sogo_1〜3 (体型総合1〜3) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS taikei_sogo_1 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS taikei_sogo_2 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS taikei_sogo_3 VARCHAR(3);

-- 82～84 uma_tokki_1〜3 (馬特記1〜3) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS uma_tokki_1 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS uma_tokki_2 VARCHAR(3);
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS uma_tokki_3 VARCHAR(3);

-- 85 uma_start_shisu (馬スタート指数) varchar(4)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS uma_start_shisu VARCHAR(4);

-- 86 uma_deokure_ritsu (馬出遅率) varchar(4)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS uma_deokure_ritsu VARCHAR(4);

-- 87 sanko_zenso (参考前走) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sanko_zenso VARCHAR(2);

-- 88 sanko_zenso_kishu_code (参考前走騎手コード) varchar(5)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS sanko_zenso_kishu_code VARCHAR(5);

-- 89 manken_shisu (万券指数) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS manken_shisu VARCHAR(3);

-- 90 manken_shirushi (万券印) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS manken_shirushi VARCHAR(1);

-- 91 kokyu_flag (コ休フラグ) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kokyu_flag VARCHAR(1);

-- 92 gekiso_type (激走タイプ) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS gekiso_type VARCHAR(2);

-- 93 kyuyo_riyu_bunrui_code (休養理由分類コード) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS kyuyo_riyu_bunrui_code VARCHAR(2);

-- 94 flag (フラグ) varchar(16)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS flag VARCHAR(16);

-- 95 nyukyu_nansome (入厩何ソメ) varchar(2)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS nyukyu_nansome VARCHAR(2);

-- 96 nyukyu_nengappi (入厩年月日) varchar(8)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS nyukyu_nengappi VARCHAR(8);

-- 97 nyukyu_nannichimae (入厩何日前) varchar(3)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS nyukyu_nannichimae VARCHAR(3);

-- 98 hobokusaki (放牧先) varchar(50)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS hobokusaki VARCHAR(50);

-- 99 hobokusaki_rank (放牧先ランク) varchar(1)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS hobokusaki_rank VARCHAR(1);

-- 100 yobi_5 (予備5) varchar(398)
ALTER TABLE jrd_kyi_fixed ADD COLUMN IF NOT EXISTS yobi_5 VARCHAR(398);

-- ============================================================================
-- 合計101カラム追加
-- 既存38カラム維持 + 101追加 = 139カラム (132 jrd_kyi + 7 derived)
-- ============================================================================
