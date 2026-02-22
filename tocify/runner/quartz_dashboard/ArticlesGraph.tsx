/**
 * Tocify Articles Dashboard graph component for Quartz.
 * Copy this file into your vault's quartz/components/ and register in index.ts and layout.
 * Only renders on the articles-dashboard page; fetches /articles.json and draws with Plotly.js.
 */
import type { QuartzComponentConstructor, QuartzComponentProps } from "./types";

const DASHBOARD_SLUG = "articles-dashboard";
const GRAPH_DIV_ID = "tocify-articles-graph";
const PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js";

function ArticlesGraph(props: QuartzComponentProps) {
  const slug = props.fileData?.slug ?? "";
  if (slug !== DASHBOARD_SLUG) {
    return null;
  }
  return (
    <div class="tocify-articles-graph-wrapper">
      <div id={GRAPH_DIV_ID} style="width:100%;height:500px;" />
    </div>
  );
}

ArticlesGraph.css = `
.tocify-articles-graph-wrapper { margin: 1rem 0; }
#tocify-articles-graph .plotly .modebar-group { display: flex; }
`;

ArticlesGraph.afterDOMLoaded = `
(function() {
  function run() {
    var div = document.getElementById('tocify-articles-graph');
    if (!div || div.dataset.drawn === '1') return;
    function loadScript(src) {
      return new Promise(function(resolve, reject) {
        var s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    function draw(data) {
      var nodes = data.nodes || [];
      var edges = data.edges || [];
      var nodeById = {};
      nodes.forEach(function(n) { nodeById[n.id] = n; });
      var articleNodes = nodes.filter(function(n) { return !n.isTopic; });
      var x = [], y = [], text = [], customdata = [];
      articleNodes.forEach(function(n) {
        x.push(n.x);
        y.push(n.y);
        text.push((n.title || n.id).substring(0, 60));
        customdata.push([n.url || '', n.topic || '']);
      });
      var traceNodes = {
        x: x, y: y, text: text, mode: 'markers',
        marker: { size: 10 },
        customdata: customdata,
        hovertemplate: '%{text}<br>Topic: %{customdata[1]}<extra></extra>',
        type: 'scatter'
      };
      var edgeX = [], edgeY = [];
      edges.forEach(function(e) {
        var a = nodeById[e.source], b = nodeById[e.target];
        if (a && b && a.x != null && b.x != null) {
          edgeX.push(a.x, b.x, null);
          edgeY.push(a.y, b.y, null);
        }
      });
      var traceEdges = {
        x: edgeX, y: edgeY, mode: 'lines',
        line: { color: 'rgba(150,150,150,0.5)', width: 1 },
        hoverinfo: 'none',
        type: 'scatter'
      };
      var layout = {
        margin: { t: 20, r: 20, b: 20, l: 20 },
        xaxis: { showgrid: false, zeroline: false, showticklabels: false },
        yaxis: { showgrid: false, zeroline: false, showticklabels: false },
        showlegend: false,
        plot_bgcolor: 'transparent',
        paper_bgcolor: 'transparent'
      };
      if (window.Plotly) {
        window.Plotly.newPlot(div, [traceEdges, traceNodes], layout, { responsive: true });
        window.Plotly.on(div, 'plotly_click', function(d) {
          var pt = d.points && d.points[0];
          if (pt && pt.customdata && pt.customdata[0]) window.open(pt.customdata[0], '_blank');
        });
        div.dataset.drawn = '1';
      }
    }
    if (window.Plotly) {
      fetch('/articles.json').then(function(r) { return r.json(); }).then(draw).catch(function(e) {
        div.innerHTML = '<p>Could not load articles graph: ' + e.message + '</p>';
      });
    } else {
      loadScript('${PLOTLY_CDN}').then(function() {
        fetch('/articles.json').then(function(r) { return r.json(); }).then(draw).catch(function(e) {
          div.innerHTML = '<p>Could not load articles graph: ' + e.message + '</p>';
        });
      }).catch(function(e) {
        div.innerHTML = '<p>Could not load Plotly: ' + e.message + '</p>';
      });
    }
  }
  run();
  document.addEventListener('nav', run);
})();
`;

export default (() => ArticlesGraph) satisfies QuartzComponentConstructor;
