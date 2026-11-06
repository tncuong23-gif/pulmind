(() => {
  'use strict';
  const palette = ['#F79767','#DA7194','#57C7E3','#F16667','#D9C8AE','#8DCC93','#ECB5C9',
    '#4C8EDA','#FFC454','#C990C0','#C4D5EB','#DFE87D','#A5ABB6','#FFDE77','#BDD9B9'];
  const distance = (x, y, ax, ay, bx, by) => {
    const dx = bx - ax, dy = by - ay;
    const t = Math.max(0, Math.min(1, ((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy || 1)));
    return Math.hypot(x-ax-t*dx, y-ay-t*dy);
  };

  window.createKGOverview = (canvas, nodes, edges, onNode, onEdge) => {
    const context = canvas.getContext('2d');
    const controller = new AbortController();
    const groups = new Map(), points = new Map(), colors = new Map();
    const types = [...new Set(nodes.map(node => node.type))].sort();
    for (const [index, type] of types.entries()) {
      groups.set(type, []);
      let hash=0;
      for(const char of type)hash=(hash*31+char.charCodeAt(0))>>>0;
      colors.set(type, palette[hash % palette.length]);
    }
    for (const node of nodes) groups.get(node.type).push(node);
    const neighbors = new Map(nodes.map(node => [node.id, []]));
    for (const edge of edges) {
      neighbors.get(edge.source)?.push(edge.target);
      neighbors.get(edge.target)?.push(edge.source);
    }
    const seeds = [...nodes].sort((a,b) => neighbors.get(b.id).length-neighbors.get(a.id).length);
    const ordered = [];
    const byId = new Map(nodes.map(node => [node.id,node]));
    for (const seed of seeds) {
      if (points.has(seed.id)) continue;
      const queue = [seed.id];
      points.set(seed.id, null);
      for (let i=0;i<queue.length;i++) {
        const id=queue[i], slot=ordered.length;
        const angle=slot*2.399963, radius=80*Math.sqrt(slot);
        const point={...byId.get(id),x:radius*Math.cos(angle),y:radius*Math.sin(angle),dx:0,dy:0};
        points.set(id,point);
        ordered.push(point);
        for (const next of neighbors.get(id)) {
          if (byId.has(next) && !points.has(next)) {points.set(next,null);queue.push(next);}
        }
      }
    }
    const links = edges.map(edge => ({edge,a:points.get(edge.source),b:points.get(edge.target)}))
      .filter(link => link.a && link.b);
    // Local repulsion through a spatial grid keeps each pass bounded on large graphs.
    for (let iteration=0;iteration<32;iteration++) {
      const grid=new Map(), cell=90;
      for (const point of ordered) {
        const key=`${Math.floor(point.x/cell)},${Math.floor(point.y/cell)}`;
        if (!grid.has(key)) grid.set(key,[]);
        grid.get(key).push(point);
        point.dx=0;point.dy=0;
      }
      for (const point of ordered) {
        const col=Math.floor(point.x/cell),row=Math.floor(point.y/cell);
        for (let i=-1;i<=1;i++) for (let j=-1;j<=1;j++) {
          const nearby=grid.get(`${col+i},${row+j}`) || [];
          const stride=Math.max(1,Math.ceil(nearby.length/12));
          for (let k=0;k<nearby.length;k+=stride) {
            const other=nearby[k],dx=point.x-other.x,dy=point.y-other.y;
            const d=Math.hypot(dx,dy);
            if (d>0 && d<cell) {
              const push=(cell-d)*.12/d;
              point.dx+=dx*push;point.dy+=dy*push;
            }
          }
        }
      }
      for (const {a,b} of links) {
        const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;
        const pull=Math.max(0,d-145)*.035/d;
        a.dx+=dx*pull;a.dy+=dy*pull;b.dx-=dx*pull;b.dy-=dy*pull;
      }
      const speed=1-iteration/60;
      for (const point of ordered) {
        point.x+=Math.max(-28,Math.min(28,point.dx))*speed;
        point.y+=Math.max(-28,Math.min(28,point.dy))*speed;
      }
    }
    const RADIUS=28, CLEARANCE=82;
    // Assign every circle a free position after relaxation. The spatial index
    // also prevents a dragged node from landing on an occupied position.
    const cells=new Map();
    const key=(x,y)=>`${Math.floor(x/CLEARANCE)},${Math.floor(y/CLEARANCE)}`;
    function remove(point) {
      cells.get(key(point.x,point.y))?.delete(point);
    }
    function insert(point) {
      const cell=key(point.x,point.y);
      if(!cells.has(cell))cells.set(cell,new Set());
      cells.get(cell).add(point);
    }
    function available(x,y,except) {
      const col=Math.floor(x/CLEARANCE),row=Math.floor(y/CLEARANCE);
      for(let i=-1;i<=1;i++)for(let j=-1;j<=1;j++) {
        for(const other of cells.get(`${col+i},${row+j}`)||[]) {
          if(other!==except && Math.hypot(other.x-x,other.y-y)<CLEARANCE)return false;
        }
      }
      return true;
    }
    function place(point,x,y) {
      let px=x,py=y,attempt=0;
      while(!available(px,py,point)) {
        attempt++;
        const radius=20*Math.sqrt(attempt), angle=attempt*2.399963;
        px=x+radius*Math.cos(angle);py=y+radius*Math.sin(angle);
      }
      remove(point);
      point.x=px;point.y=py;
      insert(point);
    }
    for(const point of ordered)place(point,point.x,point.y);
    const bundles=new Map();
    links.forEach(link=>{
      const bundle=JSON.stringify([link.a.id,link.b.id].sort());
      if(!bundles.has(bundle))bundles.set(bundle,[]);
      bundles.get(bundle).push(link);
    });
    for(const bundle of bundles.values())bundle.forEach((link,index)=>{
      link.bend=(index-(bundle.length-1)/2)*62*(link.a.id<link.b.id?1:-1);
    });
    let width,height,ratio,zoom=1,x=0,y=0,frame=0,drag,pickedNode,pickedEdge;
    let focused=null,disposed=false;
    const hiddenNodes=new Set(),hiddenEdges=new Set(),pinned=new Set();
    const menu=document.createElement('div');
    menu.className='kg-node-menu';
    menu.hidden=true;
    menu.setAttribute('role','toolbar');
    menu.setAttribute('aria-label','Thao tác với phần tử được chọn');
    canvas.parentElement.append(menu);
    const tooltip=document.createElement('div');
    tooltip.className='kg-graph-tooltip';
    tooltip.hidden=true;
    canvas.parentElement.append(tooltip);
    const visible=point=>!hiddenNodes.has(point.id)&&(!focused||focused.has(point.id));
    const visibleLink=link=>visible(link.a)&&visible(link.b)&&!hiddenEdges.has(link.edge.id);
    function geometry(link) {
      const {a,b}=link;
      const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1;
      const cx=(a.x+b.x)/2-dy/length*link.bend;
      const cy=(a.y+b.y)/2+dx/length*link.bend;
      const da=Math.hypot(cx-a.x,cy-a.y)||1,db=Math.hypot(b.x-cx,b.y-cy)||1;
      return {sx:a.x+(cx-a.x)*RADIUS/da,sy:a.y+(cy-a.y)*RADIUS/da,
        tx:b.x-(b.x-cx)*RADIUS/db,ty:b.y-(b.y-cy)*RADIUS/db,cx,cy};
    }
    function curve(g,t) {
      return {x:(1-t)**2*g.sx+2*(1-t)*t*g.cx+t*t*g.tx,
        y:(1-t)**2*g.sy+2*(1-t)*t*g.cy+t*t*g.ty};
    }
    function textLines(name) {
      const words=String(name).split(/\s+/),lines=[''];
      for(const word of words) {
        const last=lines.length-1;
        if((lines[last]+' '+word).trim().length>12 && lines[last])lines.push(word);
        else lines[last]=(lines[last]+' '+word).trim();
      }
      return lines.slice(0,3).map((line,i)=>line.slice(0,12)+(line.length>12 || (i===2&&lines.length>3)?'…':''));
    }
    function draw() {
      frame=0;
      if(disposed)return;
      context.setTransform(ratio,0,0,ratio,0,0);
      context.clearRect(0,0,width,height);
      context.translate(x,y);context.scale(zoom,zoom);
      const related=pickedNode?new Set([pickedNode.id,...neighbors.get(pickedNode.id)]):null;
      for(const link of links) {
        if(!visibleLink(link))continue;
        const selected=link===pickedEdge||link.a===pickedNode||link.b===pickedNode;
        const g=geometry(link);
        context.globalAlpha=related && !selected? .1 : 1;
        context.strokeStyle=selected?'#5f6670':'#a5abb3';
        context.lineWidth=selected?2:1;
        context.beginPath();context.moveTo(g.sx,g.sy);
        context.quadraticCurveTo(g.cx,g.cy,g.tx,g.ty);context.stroke();
        if(zoom>.24||selected) {
          const angle=Math.atan2(g.ty-g.cy,g.tx-g.cx),size=8;
          context.beginPath();context.moveTo(g.tx,g.ty);
          context.lineTo(g.tx-size*Math.cos(angle-.4),g.ty-size*Math.sin(angle-.4));
          context.lineTo(g.tx-size*Math.cos(angle+.4),g.ty-size*Math.sin(angle+.4));
          context.closePath();context.fillStyle=context.strokeStyle;context.fill();
        }
        if(zoom>.65 || (selected&&zoom>.3)) {
          const mid=curve(g,.5),px=mid.x*zoom+x,py=mid.y*zoom+y;
          if(px<0||px>width||py<0||py>height)continue;
          let angle=Math.atan2(g.ty-g.sy,g.tx-g.sx);
          if(angle>Math.PI/2||angle<-Math.PI/2)angle+=Math.PI;
          context.save();context.translate(mid.x,mid.y);context.rotate(angle);
          context.font='10px "Be Vietnam Pro", sans-serif';context.textAlign='center';
          const label=String(link.edge.type||'');
          const max=Math.max(40,Math.hypot(g.tx-g.sx,g.ty-g.sy)-30);
          const tw=Math.min(max,context.measureText(label).width)+8;
          context.fillStyle='#ffffff';context.fillRect(-tw/2,-8,tw,15);
          context.fillStyle='#545b64';context.fillText(label,0,3,max);
          context.restore();
        }
      }
      for(const point of ordered) {
        if(!visible(point))continue;
        const px=point.x*zoom+x,py=point.y*zoom+y;
        if(px<-RADIUS*zoom||px>width+RADIUS*zoom||py<-RADIUS*zoom||py>height+RADIUS*zoom)continue;
        context.globalAlpha=related && !related.has(point.id)? .16:1;
        context.beginPath();context.arc(point.x,point.y,RADIUS,0,Math.PI*2);
        context.fillStyle=colors.get(point.type);context.fill();
        context.strokeStyle=point===pickedNode?'#333c49':'#00000035';
        context.lineWidth=point===pickedNode?3:1.6;context.stroke();
        if(pinned.has(point.id)) {
          context.beginPath();context.arc(point.x+20,point.y-20,4,0,Math.PI*2);
          context.fillStyle='#364152';context.fill();
        }
        if(zoom>=.45) {
          const lines=textLines(point.name||point.id);
          context.fillStyle='#242a32';context.font='10px "Be Vietnam Pro", sans-serif';
          context.textAlign='center';context.textBaseline='middle';
          lines.forEach((line,i)=>context.fillText(line,point.x,point.y+(i-(lines.length-1)/2)*12,48));
        }
      }
      context.globalAlpha=1;context.textBaseline='alphabetic';
    }
    function refresh(){if(!frame&&!disposed)frame=requestAnimationFrame(draw);}
    function fit() {
      const shown=ordered.filter(visible);
      let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
      for(const point of shown) {
        minX=Math.min(minX,point.x);minY=Math.min(minY,point.y);
        maxX=Math.max(maxX,point.x);maxY=Math.max(maxY,point.y);
      }
      if(!shown.length){minX=minY=-50;maxX=maxY=50;}
      zoom=Math.min(1.3,(width-35)/(maxX-minX+100),(height-35)/(maxY-minY+100));
      x=width/2-(minX+maxX)*zoom/2;y=height/2-(minY+maxY)*zoom/2;
      refresh();
    }
    function resize() {
      const first=!width;
      width=Math.max(1,canvas.clientWidth);height=Math.max(1,canvas.clientHeight);
      ratio=Math.min(2,window.devicePixelRatio||1);
      canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
      if(first)fit();else refresh();
    }
    function scale(factor,px=width/2,py=height/2) {
      const next=Math.min(5,Math.max(.005,zoom*factor));
      x=px-(px-x)*next/zoom;y=py-(py-y)*next/zoom;zoom=next;
      tooltip.hidden=true;refresh();
    }
    function nodeAt(px,py) {
      const gx=(px-x)/zoom,gy=(py-y)/zoom;
      let result=null,best=RADIUS;
      for(const point of ordered) {
        if(!visible(point))continue;
        const d=Math.hypot(point.x-gx,point.y-gy);
        if(d<=best){best=d;result=point;}
      }
      return result;
    }
    function edgeAt(px,py) {
      const gx=(px-x)/zoom,gy=(py-y)/zoom;
      let result=null,best=5/zoom;
      for(const link of links) {
        if(!visibleLink(link))continue;
        const g=geometry(link);
        let a=curve(g,0);
        for(let i=1;i<=12;i++) {
          const b=curve(g,i/12),d=distance(gx,gy,a.x,a.y,b.x,b.y);
          if(d<best){best=d;result=link;}
          a=b;
        }
      }
      return result;
    }
    function action(label,handler) {
      const button=document.createElement('button');
      button.type='button';button.textContent=label;button.onclick=handler;
      menu.append(button);
    }
    function showMenu() {
      menu.replaceChildren();menu.hidden=!pickedNode&&!pickedEdge;
      if(pickedNode) {
        const node=pickedNode;
        action(pinned.has(node.id)?'Bỏ ghim':'Ghim nút',()=>{
          if(pinned.has(node.id))pinned.delete(node.id);else pinned.add(node.id);
          showMenu();refresh();
        });
        action('Xem vùng liên kết',()=>{
          focused=new Set([node.id,...neighbors.get(node.id)]);fit();
        });
        action('Ẩn nút khỏi hình',()=>{
          hiddenNodes.add(node.id);pickedNode=null;menu.hidden=true;refresh();
        });
      } else if(pickedEdge) {
        const edge=pickedEdge;
        action('Ẩn cạnh khỏi hình',()=>{
          hiddenEdges.add(edge.edge.id);pickedEdge=null;menu.hidden=true;refresh();
        });
      }
      action('Hiện lại toàn bộ',()=>{
        hiddenNodes.clear();hiddenEdges.clear();focused=null;
        pickedNode=null;pickedEdge=null;menu.hidden=true;fit();
      });
    }
    function select(px,py) {
      pickedNode=nodeAt(px,py);pickedEdge=pickedNode?null:edgeAt(px,py);
      if(pickedNode)onNode(pickedNode);
      else if(pickedEdge)onEdge(pickedEdge.edge);
      showMenu();refresh();
    }
    const listen=(type,handler)=>canvas.addEventListener(type,handler,{signal:controller.signal,passive:false});
    listen('wheel',e=>{e.preventDefault();scale(e.deltaY<0?1.13:.88,e.offsetX,e.offsetY);});
    listen('pointerdown',e=>{
      if(e.button!==0)return;
      canvas.focus({preventScroll:true});
      const node=nodeAt(e.offsetX,e.offsetY);
      drag={id:e.pointerId,x:e.clientX,y:e.clientY,originX:x,originY:y,node,
        nodeX:node?.x,nodeY:node?.y};
      canvas.setPointerCapture(e.pointerId);
    });
    listen('pointermove',e=>{
      if(drag?.id===e.pointerId) {
        if(drag.node) {
          if(!pinned.has(drag.node.id))place(drag.node,drag.nodeX+(e.clientX-drag.x)/zoom,drag.nodeY+(e.clientY-drag.y)/zoom);
        } else {x=drag.originX+e.clientX-drag.x;y=drag.originY+e.clientY-drag.y;}
        tooltip.hidden=true;refresh();return;
      }
      const node=nodeAt(e.offsetX,e.offsetY);
      tooltip.hidden=!node;
      if(node) {
        tooltip.textContent=node.name+' · '+node.type;
        tooltip.style.left=Math.min(e.offsetX+10,width-220)+'px';
        tooltip.style.top=Math.max(0,e.offsetY-48)+'px';
      }
    });
    listen('pointerup',e=>{
      if(drag?.id!==e.pointerId)return;
      if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<5)select(e.offsetX,e.offsetY);
      else if(drag.node&&!pinned.has(drag.node.id))pinned.add(drag.node.id);
      drag=null;if(pickedNode||pickedEdge)showMenu();refresh();
    });
    listen('pointercancel',()=>{drag=null;});
    listen('pointerleave',()=>{tooltip.hidden=true;});
    listen('contextmenu',e=>{e.preventDefault();select(e.offsetX,e.offsetY);});
    listen('dblclick',e=>{
      const node=nodeAt(e.offsetX,e.offsetY);
      if(node){pickedNode=node;pickedEdge=null;focused=new Set([node.id,...neighbors.get(node.id)]);fit();onNode(node);showMenu();}
    });
    listen('keydown',e=>{
      const shifts={ArrowUp:[0,35],ArrowDown:[0,-35],ArrowLeft:[35,0],ArrowRight:[-35,0]};
      if(e.key==='+'||e.key==='=')scale(1.2);
      else if(e.key==='-')scale(.8);
      else if(e.key==='Escape'){pickedNode=null;pickedEdge=null;menu.hidden=true;refresh();}
      else if(shifts[e.key]){x+=shifts[e.key][0];y+=shifts[e.key][1];refresh();}
      else return;
      e.preventDefault();
    });
    resize();
    return {colors,fit,resize,zoom:scale,
      reset(){hiddenNodes.clear();hiddenEdges.clear();focused=null;pickedNode=null;pickedEdge=null;menu.hidden=true;fit();},
      highlightEdge(index){pickedEdge=links[index]||null;if(index>=0)pickedNode=null;refresh();},
      selectNode(id){pickedNode=points.get(id)||null;pickedEdge=null;showMenu();refresh();},
      dispose(){disposed=true;controller.abort();cancelAnimationFrame(frame);menu.remove();tooltip.remove();}};
  };
})();
