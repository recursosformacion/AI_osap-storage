var kilo = require('../kilo'),
    expect = require('expect.js');

describe('#series', function() {
  it('should call functions in series', function(done) {
    var test;

    kilo.series([
      function(cbl) {
        test = 0;
        cbl(null, 1);
      },

      function(cbl) {
        expect(test).to.be(0);
        test++;
        cbl(null, 2);
      },

      function(cbl) {
        expect(test).to.be(1);
        cbl(null, 3);
      }
    ], function(e, results) {
      expect(results).to.eql([1, 2, 3]);

      done();
    });
  });

  it('should stop when an error occur', function(done) {
    kilo.series([
      function(cbl) {
        cbl(null);
      },

      function(cbl) {
        cbl(new Error('test'));
      },

      function(cbl) {
        throw new Error('Executed');
      }
    ], function(e) {
      expect(e).to.be.an(Error);
      expect(e.message).to.be('test');
      done();
    });
  });
});

describe('#parallel', function() {
  it('should call functions in (kinda) parallel', function(done) {
    var test = [];

    kilo.parallel([
      function(cbl) {
        test.push(Math.random());
        
        cbl(null, 1);
      },

      function(cbl) {
        test.push(Math.random());

        cbl(null, 2);
      },

      function(cbl) {
        test.push(Math.random());
        
        cbl(null, 3);
      }
    ], function(e, results) {
      results = results.map(function(i) {
        return i[0]
      });

      expect(results).to.eql([1, 2, 3]);
      expect(test.length).to.be(3);

      done();
    });
  });

  it('should call errCbl when an error occur', function(done) {
    kilo.parallel([
      function(cbl) {
        cbl(null);
      },

      function(cbl) {
        cbl(new Error('test'));
      }
    ], function() {}, function(e) {
      expect(e).to.be.an(Error);
      expect(e.message).to.be('test');
      done();
    });
  });
});

describe('#waterfall', function() {
  it('should call functions like waterfall', function(done) {
    kilo.waterfall([
      function(cbl) {
        cbl(null, 1);
      },

      function(arg, cbl) {
        expect(arg).to.be(1);
        cbl(null, 2, 3);
      },

      function(arg, argo, cbl) {
        expect(arg).to.be(2);
        expect(argo).to.be(3);
        cbl(null, 'done');
      }
    ], function(e, arg) {
      expect(arg).to.be('done');
      done();
    });
  });

  it('should stop when an error occur', function(done) {
    kilo.waterfall([
      function(cbl) {
        cbl(null);
      },

      function(cbl) {
        cbl(new Error('test'));
      },

      function(arg, argo, cbl) {
        throw new Error('Executed');
      }
    ], function(e) {
      expect(e).to.be.an(Error);
      expect(e.message).to.be('test');
      done();
    });
  });
});

describe('#repeat', function() {
  it('should repeat async functions', function(done) {
    var test = 0;

    kilo.repeat(500, function(cbl) {
      ++test;

      cbl(null);
    }, function(e) {
      expect(e).not.to.be.ok();
      expect(test).to.be(500);

      done();
    });
  });
});

describe('#each', function() {
  it('should async-ly call array#forEach', function(done) {
    var test = [];

    kilo.each(
      [0, 1, 2, 3, 4, 5, 6], 
      
      function(i, cbl) {
        test[i] = 1;

        cbl(null);
      },
    
      function(e) {
        expect(e).not.to.be.ok();
        expect(test).to.eql([1, 1, 1, 1, 1, 1, 1]);

        done();
      }
    );
  });

  it('should call errCbl when there is an error', function(done) {
    var test = [], times = 0;

    kilo.each(
      [0, 1, 2, 3, 4, 5, 6], 
      
      function(i, cbl) {
        test[i] = 1;

        cbl(new Error('test'));
      },
      
      function() {},

      function(e) {
        expect(e).to.be.an(Error);
        expect(e.message).to.be('test');

        if (++times === 7) done();
      }
    );
  });
});

describe('#map', function() {
  it('should async-ly call array#map', function(done) {
    kilo.map(
      [0, 1, 2, 3, 4, 5, 6], 
      
      function(i, cbl) {
        cbl(null, i + 1);
      },
    
      function(e, results) {
        expect(e).not.to.be.ok();
        expect(results).to.eql([1, 2, 3, 4, 5, 6, 7]);

        done();
      }
    );
  });

  it('should call errCbl when there is an error', function(done) {
    var times = 0;

    kilo.map(
      [0, 1, 2, 3, 4, 5, 6], 
      
      function(i, cbl) {
        cbl(new Error('test'));
      },

      function() {},
    
      function(e) {
        expect(e).to.be.an(Error);
        expect(e.message).to.be('test');

        if (++times === 7) done();
      }
    );
  });
});