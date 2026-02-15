'use client';

import dynamic from 'next/dynamic';

const Map = dynamic(() => import('./MapRender'), { ssr: false });

export default Map;
