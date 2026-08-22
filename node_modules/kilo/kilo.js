var kilo = (typeof exports !== 'undefined' ? exports : window.kilo = {});

kilo.waterfall = function(fns, cbl) { 
  if (!fns || !fns.length)
    return cbl(null);

  (function iterator() {
    var args = [].slice.call(arguments),
        e = args.shift(),
        fn = fns.shift();

    if (e)
      return cbl(e);

    if (!fn)
      return cbl.apply(cbl, [e].concat(args));

    args.push(iterator);
    fn.apply(fn, args);
  })();
};

kilo.series = function(fns, cbl) {
  var results = [];

  if (!fns || !fns.length)
    return cbl(null);
  
  (function iterator() {
    var e = arguments[0],
        fn = fns.shift();

    if (arguments.length > 1)
      results = results.concat(Array.prototype.slice.call(arguments, 1));
    
    if (!fn || e)
      return cbl(e || null, results);

    return fn(iterator);
  })();
};

kilo.parallel = function(fns, cbl, errCbl) {
  var results = new Array(fns.length),
      executed = 0;

  errCbl = errCbl || function() {};
  
  if (!fns || !fns.length)
    return cbl(null);

  var iterator = function() {
    var idx = arguments[arguments.length - 1],
        e = arguments[0];

    results[idx] = Array.prototype.slice.call(arguments, 1);
    
    if (e)
      return errCbl(e, idx);

    if (++executed === fns.length)
      return cbl(null, results);
  };
  
  for (var n = 0; n < fns.length; n++)
    fns[n](function() { // 50% faster than bind
      var args = Array.prototype.slice.call(arguments);
      args.push(n);

      iterator.apply(this, args);
    });
};

kilo.simplerParallel = function(fns, cbl, errCbl, t) { // simpler parallel, without results/idx (~70% faster)
  var executed = 0;

  errCbl = errCbl || function() {};

  if (!fns || !fns.length)
    return cbl(null);

  var iterator = function() {
    var e = arguments[0];
    
    if (e)
      return errCbl(e);

    if (++executed === fns.length)
      return cbl(null);
  };
  
  for (var n = 0; n < fns.length; n++) {
    fns[n](iterator);
  }
};

kilo.repeat = function(n, fn, cbl) {
  var fns = new Array(n);

  for (var i = 0; i < n; i++)
    fns[i] = fn;

  kilo.series(fns, cbl);
};

function each(t, list, iterator, cbl, errCbl) {
  var iterators = list.map(function(i) {
    return iterator.bind(iterator, i);
  });

  errCbl = errCbl || function() {};

  kilo[t](iterators, cbl, errCbl);
};

function map(t, list, iterator, cbl, errCbl) {
  var nlist = list.slice();

  var iterators = list.map(function(i, idx) {
    return function(fn) {
      iterator(i, function(e, what) {
        if (e)
          return fn(e);

        nlist[idx] = what;
        
        fn(null);
      });
    };
  });

  errCbl = errCbl || function() {};

  kilo[t](iterators, function() {
    cbl(null, nlist);
  }, errCbl);
};

kilo.each = kilo.eachParallel = each.bind(kilo, 'simplerParallel');
kilo.eachSeries = each.bind(kilo, 'series');

kilo.map = kilo.mapParallel = map.bind(kilo, 'simplerParallel');
kilo.mapSeries = map.bind(kilo, 'series');
