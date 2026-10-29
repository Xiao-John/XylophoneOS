// SPDX-License-Identifier: Apache-2.0
(() => {
 const assert=(x)=>{if(!x)throw Error('assertion')};
 assert(2n ** 64n === 18446744073709551616n);
 const obj={nested:{value:42}};assert(obj?.nested?.value===42 && (null??7)===7);
 const arr=new Uint8Array([1,2,255]);assert(arr.reduce((a,b)=>a+b,0)===258);
 const map=new Map([['x',42]]);assert(map.get('x')===42);
 assert(/(?<part>x+)/u.exec('xx').groups.part==='xx');
 let caught=false;try{JSON.parse('{')}catch(e){caught=e instanceof SyntaxError}assert(caught);
 globalThis.promiseDone=false;Promise.resolve(42).then(x=>{assert(x===42);globalThis.promiseDone=true});
 Promise.resolve().then(()=>{assert(globalThis.promiseDone)});
 assert(typeof document==='undefined' && typeof Worker==='undefined' && typeof WebAssembly==='undefined');
 return 'LANGUAGE_OK; DOM_WORKER_WASM_UNAVAILABLE';
})()
