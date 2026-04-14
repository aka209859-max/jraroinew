export default function Home() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <h1 className="text-4xl font-bold tracking-tight">
          Enable Edge Engine
        </h1>
        <p className="mt-4 text-lg text-gray-400">
          プロフェッショナル向け競馬データ分析プラットフォーム
        </p>
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-blue-500 transition-colors">
            <h2 className="text-xl font-semibold">データ分析</h2>
            <p className="mt-2 text-gray-400">
              2,293カラムから自由にファクターを選択し、補正回収率を分析
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-blue-500 transition-colors">
            <h2 className="text-xl font-semibold">バックテスト</h2>
            <p className="mt-2 text-gray-400">
              学習期間と検証期間を分離し、エッジの持続性を検証
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-blue-500 transition-colors">
            <h2 className="text-xl font-semibold">予測出力</h2>
            <p className="mt-2 text-gray-400">
              次走レースの全出走馬にスコアを付与し、推奨馬を提示
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
