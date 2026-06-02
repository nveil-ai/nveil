let SpriteText;
(async () => {
  SpriteText = (await import("https://esm.sh/three-spritetext")).default;
})();

(function () {
  const forceGraphComponent = {
    props: {
      // Core data and type
      graphData: Object,
      is3d: Boolean,
      
      // Node styling
      nodeColor: String,
      nodeAutoColorBy: String,
      nodeRelSize: Number,
      nodeVal: String,
      
      // Link styling
      linkColor: String,
      linkAutoColorBy: String,
      linkWidth: Number,
      linkDirectionalArrows: Boolean,
      linkOpacity: Number, // <-- Add this line to props
      
      // Layout options
      dagMode: String,
      dagLevelDistance: Number,
      
      // Physics options
      d3AlphaDecay: Number,
      d3VelocityDecay: Number,
      warmupTicks: Number,
      cooldownTicks: Number,
      cooldownTime: Number,
      
      // 3D specific options
      backgroundColor: String,
      enableNavigationControls: Boolean,
      enableNodeDrag: Boolean,
      
      // Events
      onNodeClick: Function,
      onLinkClick: Function,
    },
    
    emits: ['update-data', 'toggle-3d', 'zoom-to-fit', 'focus-on', 'node-click', 'link-click'],
    
    setup(props, { emit }) {
      const { ref, onMounted, watch, onBeforeUnmount } = Vue;
      const container = ref(null);
      let graph = null;
      
      // Create a new graph instance
      const initGraph = () => {
        if (!container.value) return;
        
        // Clear previous graph
        while (container.value.firstChild) {
          container.value.removeChild(container.value.firstChild);
        }
        
        // Create new graph instance
        graph = props.is3d ? window.ForceGraph3D() : window.ForceGraph();
        
        // Apply basic configuration
        let graphInstance = graph(container.value)
          .graphData(props.graphData || { nodes: [], links: [] });
        
        if(props.is3d==false){
          graphInstance.nodeCanvasObject((node, ctx, globalScale) => {
          const label = node.name;
          const fontSize = 12/globalScale;
          ctx.font = `${fontSize}px Sans-Serif`;
          const textWidth = ctx.measureText(label).width;
          const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2); // some padding

          ctx.fillStyle = node.color;
          ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, ...bckgDimensions);

          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          // Compute contrast color (black or white) based on node.color background
          function getContrastColor(bgColor) {
            // Parse hex color (e.g., "#RRGGBB")
            let color = bgColor;
            if (color.startsWith('#')) {
              color = color.slice(1);
            }
            if (color.length === 3) {
              color = color.split('').map(c => c + c).join('');
            }
            const r = parseInt(color.substr(0,2), 16);
            const g = parseInt(color.substr(2,2), 16);
            const b = parseInt(color.substr(4,2), 16);

            // Calculate luminance
            const luminance = (0.299*r + 0.587*g + 0.114*b)/255;
            return luminance > 0.5 ? 'rgba(0,0,0,1)' : 'rgba(255,255,255,1)';
          }

          ctx.fillStyle = getContrastColor(node.color);
          ctx.fillText(label, node.x, node.y);

          node.__bckgDimensions = bckgDimensions; // to re-use in nodePointerAreaPaint
        }).nodeCanvasObjectMode(() => 'after')
        }else{
          graphInstance.nodeThreeObject(node => {
          const sprite = new SpriteText(node.name);
          sprite.material.depthWrite = true; // make sprite background transparent
          sprite.color = "white";
          sprite.textHeight = 8;
          sprite.center.y = -0.6; // shift above node
          return sprite;
        }).nodeThreeObjectExtend(true);;
        }
        graphInstance.linkDirectionalArrowLength(6).linkDirectionalArrowRelPos(1);

        // Apply node styling
        if (props.nodeColor) {
          const nodeColor = String(props.nodeColor);
          graphInstance = graphInstance.nodeColor(nodeColor);
        }
        if (props.nodeAutoColorBy) graphInstance = graphInstance.nodeAutoColorBy(props.nodeAutoColorBy);
        if (props.nodeRelSize) graphInstance = graphInstance.nodeRelSize(props.nodeRelSize);
        if (props.nodeVal) graphInstance = graphInstance.nodeVal(props.nodeVal);
        
        // Apply link styling
        if (props.linkColor) {
          if (props.is3d) {
            graphInstance = graphInstance.linkColor(props.linkColor);
          } else {
            graphInstance = graphInstance.linkColor(props.linkColor); // <-- Always use accessor for 2D
          }
        }
        if (props.linkAutoColorBy) graphInstance = graphInstance.linkAutoColorBy(props.linkAutoColorBy);
        if (props.linkWidth) graphInstance = graphInstance.linkWidth(props.linkWidth);
        if (props.linkDirectionalArrows) graphInstance = graphInstance.linkDirectionalArrowLength(props.linkDirectionalArrows ? 6 : 0);
        if (props.is3d && props.linkOpacity !== undefined) {
          graphInstance = graphInstance.linkOpacity( props.linkOpacity );
        }
        // Apply layout options
        if (props.dagMode) graphInstance = graphInstance.dagMode(props.dagMode);
        if (props.dagLevelDistance) graphInstance = graphInstance.dagLevelDistance(props.dagLevelDistance);
        
        // Apply physics options
        if (props.d3AlphaDecay) graphInstance = graphInstance.d3AlphaDecay(props.d3AlphaDecay);
        if (props.d3VelocityDecay) graphInstance = graphInstance.d3VelocityDecay(props.d3VelocityDecay);
        if (props.warmupTicks) graphInstance = graphInstance.warmupTicks(props.warmupTicks);
        if (props.cooldownTicks) graphInstance = graphInstance.cooldownTicks(props.cooldownTicks);
        if (props.cooldownTime) graphInstance = graphInstance.cooldownTime(props.cooldownTime);
        
        // Apply 3D specific options (only if 3D mode is on)
        if (props.is3d) {
          if (props.backgroundColor) {
            // Convert color value to string explicitly to prevent # being interpreted as private field
            const bgColor = String(props.backgroundColor);
            graphInstance = graphInstance.backgroundColor(bgColor);
          }
          
          if (props.enableNavigationControls !== undefined) {
            graphInstance = graphInstance.enableNavigationControls(props.enableNavigationControls);
          }
          
          if (props.enableNodeDrag !== undefined) {
            graphInstance = graphInstance.enableNodeDrag(props.enableNodeDrag);
          }
        }
        
        // Set up event handlers
        graphInstance.onNodeClick(node => {
          emit('node-click', node);
          if (props.onNodeClick) props.onNodeClick(node);
        });
        
        graphInstance.onLinkClick(link => {
          emit('link-click', link);
          if (props.onLinkClick) props.onLinkClick(link);
        });
      };
      
      // Expose methods to the parent component
      const methods = {
        updateData: (newData) => {
          if (graph) graph.graphData(newData);
        },
        
        toggle3d: () => {
          emit('toggle-3d');
        },
        
        zoomToFit: (duration = 1000) => {
          if (graph) graph.zoomToFit(duration);
        },
        
        focusOn: (nodeId, duration = 1000) => {
          if (!graph) return;
          
          const data = graph.graphData();
          const node = data.nodes.find(n => n.id === nodeId);
          
          if (node) {
            graph.centerAt(node.x, node.y, node.z || 0, duration);
            graph.zoom(1.5, duration);
          }
        }
      };
      
      // Handle cleanup
      onBeforeUnmount(() => {
        if (graph && typeof graph.dispose === 'function') {
          graph.dispose();
        }
      });
      
      // Initialize and handle prop changes
      onMounted(initGraph);
      
      // Deep watch for graph data changes
      watch(() => props.graphData, (newData) => {
        if (graph) graph.graphData(newData);
      }, { deep: true });
      
      // Watch for dimension toggle
      watch(() => props.is3d, () => initGraph(), { immediate: false });
      
      // Watch for other prop changes that require full re-init
      const propsRequiringReinit = [
        'dagMode', 'dagLevelDistance', 'backgroundColor', 
        'enableNavigationControls', 'enableNodeDrag'
      ];
      
      propsRequiringReinit.forEach(propName => {
        watch(() => props[propName], initGraph);
      });
      
      // Watch for props that can be updated without full re-init
      watch(() => [
        props.nodeColor, props.nodeAutoColorBy, props.nodeRelSize, 
        props.linkColor, props.linkAutoColorBy, props.linkWidth, props.linkOpacity // <-- Add linkOpacity here
      ], ([nodeColor, nodeAutoColorBy, nodeRelSize, linkColor, linkAutoColorBy, linkWidth, linkOpacity]) => {
        if (!graph) return;
        
        if (nodeColor) graph.nodeColor(nodeColor);
        if (nodeAutoColorBy) graph.nodeAutoColorBy(nodeAutoColorBy);
        if (nodeRelSize) graph.nodeRelSize(nodeRelSize);
        if (linkColor) {
          if (props.is3d) {
            graph.linkColor(linkColor);
          } else {
            graph.linkColor(linkColor); // <-- Always use accessor for 2D
          }
        }
        if (linkAutoColorBy) graph.linkAutoColorBy(linkAutoColorBy);
        if (linkWidth) graph.linkWidth(linkWidth);
        if (linkOpacity !== undefined) graph.linkOpacity(linkOpacity); // <-- Add this line
      });

      return { 
        container,
        ...methods
      };
    },
    template: `<div ref="container" style="width: 100%; height: 100%;"></div>`,
  };

  // Register component with Trame's Vue app instance
  if (window.trame && window.trame.app) {
    window.trame.app.component("force-graph", forceGraphComponent);
  } else {
    console.error("Trame app instance not found, component registration failed");
  }
})();
