'use client';
import { useMemo, useState } from 'react';
import MapPreview from '@/components/MapPreview';
import it from '@/i18n/it.json';
import en from '@/i18n/en.json';

const API = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

export default function HomePage() {
  const [lang, setLang] = useState<'it' | 'en'>('it');
  const t = useMemo(() => (lang === 'it' ? (it as any) : (en as any)), [lang]);
  const [jobId, setJobId] = useState('');
  const [job, setJob] = useState<any>(null);
  const [csv, setCsv] = useState('T1,500000,5100000,120,140');

  async function submit() {
    const turbines = csv
      .trim()
      .split('\n')
      .map((r) => {
        const [id, x, y, h, d] = r.split(',');
        return { id, x: Number(x), y: Number(y), hub_height_m: Number(h), rotor_diameter_m: Number(d) };
      });
    const payload = {
      lang,
      site: { latitude: 45.2, longitude: 10.8, timezone: 'Europe/Rome', year: 2024, epsg: 32633 },
      grid: { cellsize_m: 30, bbox: null, buffer_m: 2500, nodata: -9999 },
      turbines,
      simulation: { min_solar_elevation_deg: 2 },
      output: { format: 'both' },
      calendar: { enabled: true, points: [{ id: 'P1', x: turbines[0].x + 400, y: turbines[0].y + 200 }], output_format: 'csv' }
    };
    const res = await fetch(`${API}/api/jobs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await res.json();
    setJobId(data.job_id);
    poll(data.job_id);
  }

  async function poll(id: string) {
    const timer = setInterval(async () => {
      const res = await fetch(`${API}/api/jobs/${id}`);
      const data = await res.json();
      setJob(data);
      if (['completed', 'failed'].includes(data.status)) clearInterval(timer);
    }, 2500);
  }

  async function checkout() {
    const res = await fetch(`${API}/api/jobs/${jobId}/checkout`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    window.location.href = data.checkout_url;
  }

  return (
    <main className="space-y-4">
      <header className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Wind Shadow Studio</h1>
        <button className="px-3 py-2 rounded bg-slate-200" onClick={() => setLang(lang === 'it' ? 'en' : 'it')}>{lang.toUpperCase()}</button>
      </header>
      <p>{t.ui.description}</p>
      <textarea className="w-full h-28 border rounded p-2" value={csv} onChange={(e) => setCsv(e.target.value)} />
      <button className="px-4 py-2 rounded bg-indigo-600 text-white" onClick={submit}>{t.ui.start}</button>
      {job && (
        <section className="space-y-3 bg-white p-4 rounded border">
          <div>{t.ui.status}: {job.status} - {Math.round(job.progress_pct)}%</div>
          <div>{job.progress_message}</div>
          <pre className="text-xs bg-slate-100 p-2 rounded">{JSON.stringify(job.summary, null, 2)}</pre>
          <MapPreview preview={job.preview} />
          {!job.paid && job.status === 'completed' && <button onClick={checkout} className="px-4 py-2 rounded bg-emerald-600 text-white">{t.ui.pay}</button>}
          {job.paid && (
            <div className="space-x-3">
              <a className="text-blue-600 underline" href={`${API}/download/${jobId}/asc`}>ASC</a>
              <a className="text-blue-600 underline" href={`${API}/download/${jobId}/geotiff`}>GeoTIFF</a>
              <a className="text-blue-600 underline" href={`${API}/download/${jobId}/report_pdf`}>PDF</a>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
