export default function EvidencePage({ params }: { params: { id: string } }) {
  const { id } = params;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Evidence Graph</h1>
      <p className="text-zinc-600 text-sm">Evidence ID: {id}</p>
      <div className="text-zinc-500 p-8 text-center border border-zinc-800 rounded-lg">
        Coming in Phase 3
      </div>
    </div>
  );
}
