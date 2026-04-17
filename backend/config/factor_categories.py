"""
集計キーのカテゴリ分類定義（jrd_kyi_fixed 139カラム + 他テーブル対応版）。
各キーは "テーブル名.カラム名" 形式で記述し、
analysis_engine.py が _strip_table_prefix() でカラム名のみ抽出する。

カラム名はデータローダ (data_loader_v2.py) が生成するDataFrameの列名に
完全一致させること。
"""

FACTOR_CATEGORIES: dict = {
    # =========================================================================
    # 1. JRDB総合指数
    # =========================================================================
    "JRDB総合指数": {
        "icon": "📊",
        "factors": [
            {"key": "jrd_kyi_fixed.idm",          "label": "IDM（総合指数）",   "type": "numeric"},
            {"key": "jrd_kyi_fixed.sogo_shisu",   "label": "総合指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.ninki_shisu",  "label": "人気指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.joho_shisu",   "label": "情報指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.kishu_shisu",  "label": "騎手指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.chokyo_shisu", "label": "調教指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.kyusha_shisu", "label": "厩舎指数",          "type": "numeric"},
        ],
    },
    # =========================================================================
    # 2. JRDB詳細指数
    # =========================================================================
    "JRDB詳細指数": {
        "icon": "🔢",
        "factors": [
            {"key": "jrd_kyi_fixed.ten_shisu",        "label": "テン指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.pace_shisu",       "label": "ペース指数",        "type": "numeric"},
            {"key": "jrd_kyi_fixed.agari_shisu",      "label": "上がり指数",        "type": "numeric"},
            {"key": "jrd_kyi_fixed.ichi_shisu",       "label": "位置指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.gekiso_shisu",     "label": "激走指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.manken_shisu",     "label": "万券指数",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.uma_start_shisu",  "label": "馬スタート指数",    "type": "numeric"},
        ],
    },
    # =========================================================================
    # 3. 指数順位
    # =========================================================================
    "指数順位": {
        "icon": "🏅",
        "factors": [
            {"key": "jrd_kyi_fixed.ls_shisu_juni",      "label": "LS指数順位",        "type": "numeric"},
            {"key": "jrd_kyi_fixed.ten_shisu_juni",     "label": "テン指数順位",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.pace_shisu_juni",    "label": "ペース指数順位",    "type": "numeric"},
            {"key": "jrd_kyi_fixed.agari_shisu_juni",   "label": "上がり指数順位",    "type": "numeric"},
            {"key": "jrd_kyi_fixed.ichi_shisu_juni",    "label": "位置指数順位",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.gekiso_juni",        "label": "激走順位",          "type": "numeric"},
        ],
    },
    # =========================================================================
    # 4. 基準オッズ・人気
    # =========================================================================
    "基準オッズ・人気": {
        "icon": "💰",
        "factors": [
            {"key": "jrd_kyi_fixed.kijun_odds_tansho",        "label": "基準オッズ単勝",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.kijun_odds_fukusho",       "label": "基準オッズ複勝",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.kijun_ninkijun_tansho",    "label": "基準人気順単勝",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.kijun_ninkijun_fukusho",   "label": "基準人気順複勝",      "type": "numeric"},
            {"key": "jrd_sed.tansho_odds",                    "label": "単勝オッズ（確定）",  "type": "numeric"},
            {"key": "jrd_sed.odds_fukusho",                   "label": "複勝オッズ（確定）",  "type": "numeric"},
            {"key": "jrd_sed.tansho_ninkijun",                "label": "単勝人気（確定）",    "type": "numeric"},
        ],
    },
    # =========================================================================
    # 5. 展開予想
    # =========================================================================
    "展開予想": {
        "icon": "🗺",
        "factors": [
            {"key": "jrd_kyi_fixed.pace_yoso",         "label": "ペース予想",        "type": "code"},
            {"key": "jrd_kyi_fixed.dochu_juni",        "label": "道中順位",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.dochu_sa",          "label": "道中差",            "type": "numeric"},
            {"key": "jrd_kyi_fixed.dochu_uchisoto",    "label": "道中内外",          "type": "code"},
            {"key": "jrd_kyi_fixed.kohan_3f_juni",     "label": "後半3F順位",        "type": "numeric"},
            {"key": "jrd_kyi_fixed.kohan_3f_sa",       "label": "後半3F差",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.kohan_3f_uchisoto", "label": "後半3F内外",        "type": "code"},
            {"key": "jrd_kyi_fixed.goal_juni",         "label": "ゴール順位",        "type": "numeric"},
            {"key": "jrd_kyi_fixed.goal_sa",           "label": "ゴール差",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.goal_uchisoto",     "label": "ゴール内外",        "type": "code"},
            {"key": "jrd_kyi_fixed.tenkai_kigo_code",  "label": "展開記号コード",    "type": "code"},
            {"key": "jrd_kyi_fixed.kyakushitsu",       "label": "脚質（予測）",      "type": "code"},
            {"key": "jrd_sed.kyakushitsu_code",        "label": "脚質（確定）",      "type": "code"},
        ],
    },
    # =========================================================================
    # 6. 馬体・装備
    # =========================================================================
    "馬体・装備": {
        "icon": "🦴",
        "factors": [
            {"key": "jrd_kyi_fixed.hizume_code",   "label": "蹄コード",          "type": "code"},
            {"key": "jrd_kyi_fixed.blinker",       "label": "ブリンカー",        "type": "code"},
            {"key": "jrd_kyi_fixed.taikei",        "label": "体型",              "type": "code"},
            {"key": "jrd_kyi_fixed.taikei_sogo_1", "label": "体型総合1",         "type": "numeric"},
            {"key": "jrd_kyi_fixed.taikei_sogo_2", "label": "体型総合2",         "type": "numeric"},
            {"key": "jrd_kyi_fixed.taikei_sogo_3", "label": "体型総合3",         "type": "numeric"},
            {"key": "jrd_kyi_fixed.uma_tokki_1",   "label": "馬特記1",           "type": "code"},
            {"key": "jrd_kyi_fixed.uma_tokki_2",   "label": "馬特記2",           "type": "code"},
            {"key": "jrd_kyi_fixed.uma_tokki_3",   "label": "馬特記3",           "type": "code"},
            {"key": "jrd_kyi_fixed.soho",          "label": "走法",              "type": "code"},
            {"key": "jrd_sed.bataiju",             "label": "馬体重（確定）",    "type": "numeric"},
            {"key": "jrd_sed.bataiju_zogen",       "label": "馬体重増減（確定）","type": "numeric"},
        ],
    },
    # =========================================================================
    # 7. 適性
    # =========================================================================
    "適性": {
        "icon": "🎯",
        "factors": [
            {"key": "jrd_kyi_fixed.kyori_tekisei",       "label": "距離適性",      "type": "code"},
            {"key": "jrd_kyi_fixed.kyori_tekisei_2",     "label": "距離適性2",     "type": "code"},
            {"key": "jrd_kyi_fixed.shiba_tekisei_code",  "label": "芝適性",        "type": "code"},
            {"key": "jrd_kyi_fixed.da_tekisei_code",     "label": "ダート適性",    "type": "code"},
            {"key": "jrd_kyi_fixed.omo_tekisei_code",    "label": "重馬場適性",    "type": "code"},
        ],
    },
    # =========================================================================
    # 8. クラス・条件
    # =========================================================================
    "クラス・条件": {
        "icon": "🏆",
        "factors": [
            {"key": "jrd_kyi_fixed.class_code",       "label": "クラスコード",        "type": "code"},
            {"key": "jrd_kyi_fixed.joshodo_code",      "label": "上昇度コード",        "type": "code"},
            {"key": "jrd_kyi_fixed.joken_class_code",  "label": "条件クラスコード",    "type": "code"},
            {"key": "jrd_sed.grade_code",              "label": "グレードコード",      "type": "code"},
            {"key": "jrd_sed.kyoso_shubetsu_code",     "label": "競走種別コード",      "type": "code"},
            {"key": "jrd_sed.kyoso_joken_code",        "label": "競走条件コード",      "type": "code"},
        ],
    },
    # =========================================================================
    # 9. 騎手・調教師
    # =========================================================================
    "騎手・調教師": {
        "icon": "👤",
        "factors": [
            {"key": "jrd_kyi_fixed.kishu_code",                    "label": "騎手コード",          "type": "code"},
            {"key": "jrd_kyi_fixed.chokyoshi_code",                "label": "調教師コード",        "type": "code"},
            {"key": "jrd_kyi_fixed.kishu_kitai_rentai_ritsu",      "label": "騎手期待連対率",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.kishu_kitai_tansho_ritsu",      "label": "騎手期待単勝率",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.kishu_kitai_sanchakunai_ritsu", "label": "騎手期待3着内率",     "type": "numeric"},
            {"key": "jrd_kyi_fixed.kishumei",                      "label": "騎手名",              "type": "code"},
            {"key": "jrd_kyi_fixed.chokyoshimei",                  "label": "調教師名",            "type": "code"},
            {"key": "jrd_kyi_fixed.chokyoshi_shozoku",             "label": "調教師所属",          "type": "code"},
            {"key": "jrd_kyi_fixed.kishu_minarai_code",            "label": "騎手見習コード",      "type": "code"},
            {"key": "jrd_kyi_fixed.kyusha_rank",                   "label": "厩舎ランク",          "type": "code"},
            {"key": "jrd_kyi_fixed.kyusha_hyoka_code",             "label": "厩舎評価コード",      "type": "code"},
            {"key": "jrd_kyi_fixed.chokyo_yajirushi_code",         "label": "調教矢印コード",      "type": "code"},
        ],
    },
    # =========================================================================
    # 10. JRDB印
    # =========================================================================
    "JRDB印": {
        "icon": "🔖",
        "factors": [
            {"key": "jrd_kyi_fixed.shirushi_code_1", "label": "印コード1（本紙）",    "type": "code"},
            {"key": "jrd_kyi_fixed.shirushi_code_2", "label": "印コード2（IDM）",     "type": "code"},
            {"key": "jrd_kyi_fixed.shirushi_code_3", "label": "印コード3（情報）",    "type": "code"},
            {"key": "jrd_kyi_fixed.shirushi_code_4", "label": "印コード4（騎手）",    "type": "code"},
            {"key": "jrd_kyi_fixed.shirushi_code_5", "label": "印コード5（厩舎）",    "type": "code"},
            {"key": "jrd_kyi_fixed.shirushi_code_6", "label": "印コード6（調教）",    "type": "code"},
            {"key": "jrd_kyi_fixed.shirushi_code_7", "label": "印コード7（激走）",    "type": "code"},
            {"key": "jrd_kyi_fixed.manken_shirushi",  "label": "万券印",               "type": "code"},
        ],
    },
    # =========================================================================
    # 11. レース条件
    # =========================================================================
    "レース条件": {
        "icon": "🏇",
        "factors": [
            {"key": "jrd_kyi_fixed.keibajo_code",  "label": "競馬場コード",      "type": "code"},
            {"key": "jrd_sed.track_code",          "label": "トラックコード",    "type": "code"},
            {"key": "jrd_sed.kyori",               "label": "距離（m）",         "type": "numeric"},
            {"key": "jrd_sed.babajotai_code",      "label": "馬場状態コード",    "type": "code"},
            {"key": "jrd_sed.tenko_code",          "label": "天候コード",        "type": "code"},
        ],
    },
    # =========================================================================
    # 12. ローテーション・厩舎
    # =========================================================================
    "ローテーション・厩舎": {
        "icon": "🔄",
        "factors": [
            {"key": "jrd_kyi_fixed.rotation",              "label": "ローテーション",      "type": "numeric"},
            {"key": "jrd_kyi_fixed.sanko_zenso",           "label": "参考前走",            "type": "numeric"},
            {"key": "jrd_kyi_fixed.kyuyo_riyu_bunrui_code","label": "休養理由分類コード",  "type": "code"},
            {"key": "jrd_kyi_fixed.nyukyu_nansome",        "label": "入厩何ソメ",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.nyukyu_nannichimae",    "label": "入厩何日前",          "type": "numeric"},
            {"key": "jrd_kyi_fixed.nyukyu_nengappi",       "label": "入厩年月日",          "type": "code"},
            {"key": "jrd_kyi_fixed.hobokusaki_rank",       "label": "放牧先ランク",        "type": "code"},
            {"key": "jrd_kyi_fixed.kokyu_flag",            "label": "コ休フラグ",          "type": "code"},
            {"key": "jrd_kyi_fixed.yuso_kubun",            "label": "輸送区分",            "type": "code"},
        ],
    },
    # =========================================================================
    # 13. 血統
    # =========================================================================
    "血統": {
        "icon": "🧬",
        "factors": [
            {"key": "jrd_ukc.bamei_chichi",           "label": "父馬名",              "type": "code"},
            {"key": "jrd_ukc.bamei_haha",             "label": "母馬名",              "type": "code"},
            {"key": "jrd_ukc.bamei_hahachichi",       "label": "母父馬名（BMS）",     "type": "code"},
            {"key": "jrd_ukc.keito_code_chichi",      "label": "父系統コード",        "type": "code"},
            {"key": "jrd_ukc.keito_code_hahachichi",  "label": "母父系統コード",      "type": "code"},
            {"key": "jrd_kka.seiseki_chichi_1",       "label": "父成績1",             "type": "numeric"},
            {"key": "jrd_kka.seiseki_chichi_2",       "label": "父成績2",             "type": "numeric"},
            {"key": "jrd_kka.seiseki_chichi_3",       "label": "父成績3",             "type": "numeric"},
            {"key": "jrd_kka.seiseki_hahachichi_1",   "label": "母父成績1",           "type": "numeric"},
            {"key": "jrd_kka.seiseki_hahachichi_2",   "label": "母父成績2",           "type": "numeric"},
            {"key": "jrd_kka.seiseki_hahachichi_3",   "label": "母父成績3",           "type": "numeric"},
        ],
    },
    # =========================================================================
    # 14. 直前情報
    # =========================================================================
    "直前情報": {
        "icon": "⚡",
        "factors": [
            {"key": "jrd_tyb.paddock_shisu",          "label": "パドック指数",        "type": "numeric"},
            {"key": "jrd_tyb.odds_shisu",             "label": "オッズ指数（直前）",  "type": "numeric"},
            {"key": "jrd_tyb.chokuzen_sogo_shirushi", "label": "直前総合印",          "type": "code"},
            {"key": "jrd_tyb.batai_code",             "label": "馬体コード（直前）",  "type": "code"},
            {"key": "jrd_tyb.kehai_code",             "label": "気配コード（直前）",  "type": "code"},
        ],
    },
    # =========================================================================
    # 15. 馬具・脚元
    # =========================================================================
    "馬具・脚元": {
        "icon": "🦶",
        "factors": [
            {"key": "jrd_skb.tokki_code",    "label": "特記コード",    "type": "code"},
            {"key": "jrd_skb.bagu_code",     "label": "馬具コード",    "type": "code"},
            {"key": "jrd_skb.hami",          "label": "ハミ",          "type": "code"},
            {"key": "jrd_skb.bandage",       "label": "バンテージ",    "type": "code"},
            {"key": "jrd_skb.teitetsu",      "label": "蹄鉄",          "type": "code"},
            {"key": "jrd_skb.hizume_jotai",  "label": "蹄状態",        "type": "code"},
            {"key": "jrd_skb.soe",           "label": "ソエ",          "type": "code"},
            {"key": "jrd_skb.kotsuryu",      "label": "骨瘤",          "type": "code"},
        ],
    },
    # =========================================================================
    # 16. 調教
    # =========================================================================
    "調教": {
        "icon": "🏋",
        "factors": [
            {"key": "jrd_cha.chokyo_f",        "label": "調教F",           "type": "numeric"},
            {"key": "jrd_cha.ten_f",           "label": "テンF",           "type": "numeric"},
            {"key": "jrd_cha.chukan_f",        "label": "中間F",           "type": "numeric"},
            {"key": "jrd_cha.shimai_f",        "label": "しまいF",         "type": "numeric"},
            {"key": "jrd_cha.ten_f_shisu",     "label": "テンF指数",       "type": "numeric"},
            {"key": "jrd_cha.chukan_f_shisu",  "label": "中間F指数",       "type": "numeric"},
            {"key": "jrd_cha.shimai_f_shisu",  "label": "しまいF指数",     "type": "numeric"},
            {"key": "jrd_cha.oikiri_shisu",    "label": "追切指数",        "type": "numeric"},
        ],
    },
    # =========================================================================
    # 17. レースペース・結果
    # =========================================================================
    "レースペース・結果": {
        "icon": "🏁",
        "factors": [
            {"key": "jrd_sed.race_pace",       "label": "レースペース",    "type": "code"},
            {"key": "jrd_sed.uma_pace",        "label": "馬ペース",        "type": "code"},
            {"key": "jrd_sed.corner_1",        "label": "コーナー1通過順", "type": "numeric"},
            {"key": "jrd_sed.corner_2",        "label": "コーナー2通過順", "type": "numeric"},
            {"key": "jrd_sed.corner_3",        "label": "コーナー3通過順", "type": "numeric"},
            {"key": "jrd_sed.corner_4",        "label": "コーナー4通過順", "type": "numeric"},
            {"key": "jrd_sed.zenhan_3f_taimu", "label": "前半3Fタイム",    "type": "numeric"},
            {"key": "jrd_sed.kohan_3f",        "label": "後半3F",          "type": "numeric"},
        ],
    },
    # =========================================================================
    # 18. フラグ・特定情報
    # =========================================================================
    "フラグ・特定情報": {
        "icon": "🚩",
        "factors": [
            {"key": "jrd_kyi_fixed.flag",            "label": "フラグ",          "type": "code"},
            {"key": "jrd_kyi_fixed.gekiso_type",     "label": "激走タイプ",      "type": "code"},
            {"key": "jrd_kyi_fixed.tokutei_joho_1",  "label": "特定情報1",       "type": "code"},
            {"key": "jrd_kyi_fixed.tokutei_joho_2",  "label": "特定情報2",       "type": "code"},
            {"key": "jrd_kyi_fixed.tokutei_joho_3",  "label": "特定情報3",       "type": "code"},
            {"key": "jrd_kyi_fixed.tokutei_joho_4",  "label": "特定情報4",       "type": "code"},
            {"key": "jrd_kyi_fixed.tokutei_joho_5",  "label": "特定情報5",       "type": "code"},
            {"key": "jrd_kyi_fixed.sogo_joho_1",     "label": "総合情報1",       "type": "code"},
            {"key": "jrd_kyi_fixed.sogo_joho_2",     "label": "総合情報2",       "type": "code"},
            {"key": "jrd_kyi_fixed.sogo_joho_3",     "label": "総合情報3",       "type": "code"},
            {"key": "jrd_kyi_fixed.sogo_joho_4",     "label": "総合情報4",       "type": "code"},
            {"key": "jrd_kyi_fixed.sogo_joho_5",     "label": "総合情報5",       "type": "code"},
            {"key": "jrd_kyi_fixed.torikeshi_flag",  "label": "取消フラグ",      "type": "code"},
        ],
    },
}
